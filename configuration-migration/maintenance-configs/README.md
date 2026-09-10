# Maintenance Configurations Migration

Migrates Instana maintenance windows (maintenance configurations) between
backends, including their schedule, scope query, and tag filters.

## Quick Start

```bash
# Copy maintenance configurations, leaving any that already exist untouched
uv run cli.py maintenance-configs --on-duplicate skip --config-file config.ini

# Overwrite existing ones with the source version
uv run cli.py maintenance-configs --on-duplicate update --config-file config.ini
```

## Why this resource migrates cleanly

Most Instana resources generate their own IDs on create, so a migration tool
has to match items across backends by name — which is fragile, because a rename
in the target produces a duplicate and near-identical names collide.

Maintenance configurations are different: **the create endpoint takes the ID
from the caller.** `PUT /api/settings/v2/maintenance/{id}` is create-or-update,
and `id` is a required field in the request body. So this migrator **preserves
source IDs in the target**, which means:

- Identity is exact rather than name-based
- Renaming a window in the target does not create a duplicate
- Re-running is naturally idempotent — the same ID is simply written again
- A window can be traced back to its source, one to one

There is also nothing to translate across backends. The scope is a Dynamic
Focus Query *string*, and tag filters are string-keyed comparisons — no
references to other resources' IDs, and no credentials anywhere.

## Endpoints used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/settings/v2/maintenance` | GET | List all configurations |
| `/api/settings/v2/maintenance/{id}` | PUT | Create **or** update, keyed on the ID |

> **v1 is deprecated.** `/api/settings/maintenance` still exists but is marked
> deprecated in Instana's API specification. This migrator uses v2 only.

Not used: `DELETE /{id}`, and `PUT /{id}/pause` and `/{id}/resume`. Nothing is
ever deleted from the target, and the paused state travels as part of the
configuration itself (the `paused` field), so the dedicated endpoints are not
needed.

## What is migrated

Everything the write endpoint accepts:

| Field | Notes |
|-------|-------|
| `id` | Preserved from the source |
| `name` | |
| `query` | Dynamic Focus Query defining which entities the window covers. May be an empty string, meaning the window is not scoped to a subset of entities — this is common and migrates normally |
| `scheduling` | See [Scheduling](#scheduling) |
| `paused` | Whether the window is currently paused |
| `retriggerOpenAlertsEnabled` | Whether open alerts re-fire after the window |
| `tagFilterExpression` | Recursive AND/OR tree of tag filters |
| `tagFilterExpressionEnabled` | Whether that expression is applied |

### Fields deliberately dropped

The list endpoint returns five fields the write endpoint does not accept. They
are all computed by the server and are stripped before writing:

`applicationNames`, `occurrence`, `invalid`, `lastUpdated`, `state`

Sending any of them would cause the request to be rejected.

## Scheduling

The `scheduling` object is polymorphic on its `type`:

**`ONE_TIME`** — `{type, start, duration}`

**`RECURRENT`** — `{type, start, duration, rrule, timezoneId}`

`duration` is `{amount, unit}` where `unit` is `MINUTES`, `HOURS` or `DAYS`.
`start` is an epoch timestamp in milliseconds. `rrule` is an iCalendar
recurrence rule, e.g. `FREQ=WEEKLY;BYDAY=SU`.

A configuration is skipped, with a message, if it is missing `type`, `start` or
`duration`, or if it is `RECURRENT` without an `rrule` — those would be rejected
by the API anyway.

## Two things to expect

**Elapsed windows cannot be migrated at all.** The backend refuses to create a
window that has already run, answering:

```
400  {"errors": ["The maintenance window is already expired."]}
```

The same applies to windows in the `UNSCHEDULED` state. This restriction is not
in the API specification — it was found by running the migration against a real
backend. Since the rule is deterministic, the migrator detects these up front and
counts them as **skipped**, with a grouped summary of the reasons, rather than
issuing requests that are certain to fail.

This affects recurrent windows too, not just one-time ones: a recurrent schedule
expires once its `rrule` exhausts an `UNTIL` date or `COUNT`. Expiry is therefore
read from the `state` field the source backend computes, rather than inferred
from the start time, which would miss those.

**Expect this to account for most of a long-lived source.** On a shared test
environment, 159 of 183 windows were already expired or unscheduled, so only 24
were migratable. That is the correct result, not a failure — those windows cannot
be recreated anywhere.

When reading from a hand-written file with no `state` field, the migrator can
only infer expiry for one-time windows. An expired recurrent window in such a
file will be attempted and reported as a genuine failure.

**A query can reference entities the target does not have.** A window scoped to
`entity.zone:prod-us` writes successfully but matches nothing if that zone does
not exist in the target. This cannot be detected from the API, so review your
queries after migrating between environments with different topologies.

## Duplicate handling

Matching is by ID, so "already exists" means the exact same configuration.

| `--on-duplicate` | Behavior |
|------------------|----------|
| `skip` | Existing configurations are left untouched |
| `update` | Existing configurations are overwritten with the source version |
| *(unset)* | Prompts per configuration: `[s]` skip, `[u]` update, `[c]` cancel. Falls back to `skip` when there is no TTY |

`--on-duplicate` accepts `skip`, `update` and `cancel` on the command line. The
interactive prompt is the default and is selected by *omitting* the flag, or by
setting `on_duplicate = ask` in `config.ini`.

> **`update` overwrites the target's version wherever it differs.** Maintenance
> windows suppress alerting, so an incorrect one can silence alerts that should
> have fired. Confirm the source is authoritative before using `update` against
> production.

## Result shape

```python
{
  "source": 12,     # configurations found in the source
  "migrated": 3,    # did not exist in the target, created
  "updated": 2,     # already existed, overwritten
  "skipped": 7,     # left alone, unusable, or expired/unscheduled
  "failed": 0,      # the write was attempted and rejected
}
```

## Exit codes

Like the other migrators, the CLI exits `0` when `migrated > 0 or updated > 0`
and `1` otherwise. **An idempotent re-run in `skip` mode therefore exits `1`** —
nothing needed changing. Exit `1` means "nothing changed", not "something
broke"; check the `failed` count to tell them apart.

## API token permissions

Both tokens need **`CanConfigureMaintenanceWindows`**. Unusually, that single
permission covers reading as well as writing, so a source token without it
cannot even list configurations.

## Configuration

```ini
[source]
token = your_source_api_token
url = https://source-instana.example.com

[target]
token = your_target_api_token
url = https://target-instana.example.com

[general]
verify_ssl = true
on_duplicate = skip
request_timeout = 30
```

This migrator is synchronous and honours `--request-timeout`. The concurrency
options (`--max-concurrent`, `--rate-limit`, `--retry-attempts`) are not used
and are deliberately absent from this subcommand: maintenance windows number in
the tens and need one request each.

## File-based source

```bash
# Fetch from the API; the result is also saved locally
uv run cli.py maintenance-configs --events-source api \
  --events-file-path my_windows.json --config-file config.ini

# Migrate from that file instead of reading the source backend
uv run cli.py maintenance-configs --events-source file \
  --events-file-path my_windows.json --config-file config.ini
```

The export format is an envelope:

```json
{
  "version": 1,
  "resource": "maintenance-configs",
  "exportedAt": "2026-08-13T12:00:00+00:00",
  "sourceUrl": "https://source-instana.example.com",
  "maintenanceConfigs": [
    {
      "id": "abc123",
      "name": "Nightly patching",
      "query": "entity.zone:production",
      "scheduling": {
        "type": "RECURRENT",
        "start": 1700000000000,
        "duration": {"amount": 2, "unit": "HOURS"},
        "rrule": "FREQ=WEEKLY;BYDAY=SU",
        "timezoneId": "Europe/Berlin"
      },
      "paused": false,
      "retriggerOpenAlertsEnabled": true,
      "tagFilterExpressionEnabled": false
    }
  ]
}
```

A plain JSON array of configurations is also accepted.

> `events_file_path` is shared by every migrator and defaults to
> `source_events.json`. To avoid overwriting the custom events data file, this
> migrator writes to `source_maintenance_configs.json` when the path is still
> that default, and says so. Pass `--events-file-path` to choose explicitly.
