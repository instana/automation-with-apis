# Instana Configuration Migration Tool

A comprehensive, enterprise-grade tool for migrating Instana configurations between different environments, instances, and organisations. This tool streamlines the process of moving custom events, alert channels, alert configurations, application and service configurations, smart alerts, custom dashboards, and more.

## Overview

The Instana Configuration Migration Tool is designed to solve real-world challenges faced by DevOps teams, SREs, and platform engineers who need to:

- **Standardize configurations** across multiple Instana environments (dev, staging, production)
- **Migrate configurations** when upgrading Instana versions or moving between instances
- **Replicate successful configurations** from one environment to another
- **Backup and restore** critical monitoring configurations
- **Preview changes safely** with a built-in dry-run mode before writing anything

## Supported Resources

| # | Resource | CLI subcommand |
|---|---|---|
| 1 | Custom Event Specifications | `events` |
| 2 | Alert Channels | `channels` |
| 3 | Alert Configurations | `configs` |
| 4 | Application Configurations | `applications` |
| 5 | Service Configurations | `services` |
| 6 | Endpoint Configurations | `endpoints` |
| 7 | Custom Dashboards | `custom-dashboards` |
| 8 | Maintenance Configurations | `maintenance-configs` |
| 9 | Website Configurations | `website-configs` |
| 10 | Application Smart Alerts | `application-smart-alerts` |
| 11 | Website Smart Alerts | `website-smart-alerts` |
| 12 | Mobile App Smart Alerts | `mobile-app-smart-alerts` |
| 13 | Infrastructure Smart Alerts | `infrastructure-smart-alerts` |

### Resource details

**Custom Event Specifications** — event rules and conditions, metric patterns and thresholds, severity levels, entity type filtering.

**Alert Channels** — email, Slack, webhook, PagerDuty, and other notification channels.

**Alert Configurations** — alert rules and threshold conditions, time windows, alert channel mappings.

**Application Configurations** — Application Perspectives with boundary scope, match specifications, access rules, and tag filter expressions.

**Service Configurations** — custom service rules, match specifications, service labels.

**Endpoint Configurations** — custom endpoint mapping rules per service, path template rules, first-path-segment rules. Scoped by service ID; use `--on-duplicate update` when source and target share the same service IDs.

**Custom Dashboards** — dashboard widgets, layouts, access rules, user mapping from source to target by email. Supports async migration for improved performance.

**Maintenance Configurations** — maintenance windows (one-time and recurring), schedules with recurrence rules and time zones, scope queries and tag filter expressions. See [maintenance-configs/README.md](maintenance-configs/README.md) for full details.

**Website Configurations** — website monitoring configurations, name matching, duplicate detection.

**Smart Alerts (Application / Website / Mobile App / Infrastructure)** — smart alert configurations with alert channel remapping to target IDs. Application smart alerts additionally remap application IDs; website smart alerts remap website IDs; mobile app smart alerts remap mobile app IDs. All four support `--dry-run` and `--on-duplicate`.

## Installation

### Prerequisites

- **Python 3.8+** (3.9+ recommended)
- **uv** package manager (recommended) or pip
- **API tokens** for both source and target Instana instances
- **Network connectivity** to both Instana instances

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/instana/automation-with-apis.git
cd automation-with-apis/configuration-migration

# Install dependencies
uv sync

# Verify installation
uv run instana-migrate --help
```

### Using pip (Alternative)

```bash
git clone https://github.com/instana/automation-with-apis.git
cd automation-with-apis/configuration-migration

pip install -r requirements.txt
python cli.py --help
```

## Usage

### Command Line Interface

The tool provides a unified CLI with one subcommand per resource type. Every subcommand accepts the same core flags:

| Flag | Description |
|---|---|
| `--source-token` | API token for the source Instana backend |
| `--source-url` | Base URL of the source backend |
| `--target-token` | API token for the target Instana backend |
| `--target-url` | Base URL of the target backend |
| `--config-file` | Path to an INI configuration file |
| `--no-verify-ssl` | Disable SSL certificate verification |
| `--events-source` | `api` (default) or `file` |
| `--events-file-path` | Path to the local JSON file when using `--events-source file` |
| `--on-duplicate` | `skip`, `update`, or `cancel` (default: interactive prompt) |
| `--dry-run` | Preview changes without writing anything |

---

#### Dry Run (Preview Before Migrating)

All subcommands support `--dry-run`. It connects to both backends, checks permissions, compares source and target configurations, then prints a per-item preview of what *would* happen — without writing anything to the target.

```bash
# Using a config file
uv run cli.py events --dry-run --config-file config.ini

# Passing credentials directly on the command line
uv run cli.py events \
  --dry-run \
  --source-token YOUR_SOURCE_TOKEN \
  --source-url https://source-backend.example.com \
  --target-token YOUR_TARGET_TOKEN \
  --target-url https://target-backend.example.com

# Works with every subcommand — just swap the subcommand name
uv run cli.py channels \
  --dry-run \
  --source-token YOUR_SOURCE_TOKEN \
  --source-url https://source-backend.example.com \
  --target-token YOUR_TARGET_TOKEN \
  --target-url https://target-backend.example.com

# Combine with other flags — e.g. read source from a local file
uv run cli.py events \
  --dry-run \
  --events-source file \
  --events-file-path source_events.json \
  --target-token YOUR_TARGET_TOKEN \
  --target-url https://target-backend.example.com
```

Dry run can also be enabled via the config file (`dry_run = true` under `[general]`) or the environment variable `EVENTS_MIGRATOR_DRY_RUN=true`.

---

#### Custom Events Migration

```bash
# Basic usage with command line arguments
uv run cli.py events --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                     --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Using a configuration file
uv run cli.py events --config-file config.ini

# Disable SSL verification (not recommended for production)
uv run cli.py events --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Use events from a local file instead of fetching from API
uv run cli.py events --events-source file --events-file-path source_events.json \
                     --target-token TOKEN --target-url URL

# Fetch events from API but save to a file for future use
uv run cli.py events --events-source api --events-file-path my_events.json \
                     --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Alert Channels Migration

```bash
# Basic usage with command line arguments
uv run cli.py channels --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                       --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Using a configuration file
uv run cli.py channels --config-file config.ini

# Disable SSL verification (not recommended for production)
uv run cli.py channels --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Use alert channels from a local file instead of fetching from API
uv run cli.py channels --events-source file --events-file-path source_alert_channels.json \
                       --target-token TOKEN --target-url URL

# Fetch alert channels from API but save to a file for future use
uv run cli.py channels --events-source api --events-file-path my_alert_channels.json \
                       --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Alert Configurations Migration

```bash
# Basic usage with command line arguments
uv run cli.py configs --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                      --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Using a configuration file
uv run cli.py configs --config-file config.ini

# Disable SSL verification (not recommended for production)
uv run cli.py configs --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Use alert configurations from a local file instead of fetching from API
uv run cli.py configs --events-source file --events-file-path source_alert_configs.json \
                      --target-token TOKEN --target-url URL

# Fetch alert configurations from API but save to a file for future use
uv run cli.py configs --events-source api --events-file-path my_alert_configs.json \
                      --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Application Configurations Migration

```bash
# Basic usage
uv run cli.py applications --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                           --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Skip existing application configs
uv run cli.py applications --on-duplicate skip --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Update existing application configs
uv run cli.py applications --on-duplicate update --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Disable SSL verification
uv run cli.py applications --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Service Configurations Migration

```bash
# Basic usage
uv run cli.py services --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                       --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Skip existing service configs
uv run cli.py services --on-duplicate skip --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Update existing service configs
uv run cli.py services --on-duplicate update --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Disable SSL verification
uv run cli.py services --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Endpoint Configurations Migration

```bash
# Basic usage
uv run cli.py endpoints --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                        --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Update existing endpoint configs (use when source and target share the same service IDs)
uv run cli.py endpoints --on-duplicate update --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Disable SSL verification
uv run cli.py endpoints --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Custom Dashboards Migration

```bash
# Basic usage
uv run cli.py custom-dashboards --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                                --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Skip existing dashboards
uv run cli.py custom-dashboards --on-duplicate skip --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Update existing dashboards
uv run cli.py custom-dashboards --on-duplicate update --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL

# Disable SSL verification
uv run cli.py custom-dashboards --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

#### Maintenance Configurations Migration

```bash
# Basic usage with command line arguments
uv run cli.py maintenance-configs --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                                  --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Using a configuration file
uv run cli.py maintenance-configs --config-file config.ini

# Leave existing maintenance windows untouched
uv run cli.py maintenance-configs --on-duplicate skip --config-file config.ini

# Overwrite existing maintenance windows with the source version
uv run cli.py maintenance-configs --on-duplicate update --config-file config.ini

# Use maintenance configurations from a local file instead of the API
uv run cli.py maintenance-configs --events-source file --events-file-path my_windows.json \
                                  --target-token TOKEN --target-url URL
```

Both tokens need the `CanConfigureMaintenanceWindows` permission, which covers
reading as well as writing. Note that `--on-duplicate update` overwrites the
target's windows: since maintenance windows suppress alerting, confirm the
source is authoritative before running it against production.

#### Website Configurations Migration

```bash
# Basic usage with command line arguments
uv run cli.py website-configs --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com \
                              --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com

# Using a configuration file
uv run cli.py website-configs --config-file config.ini

# Skip existing website configurations in target
uv run cli.py website-configs --on-duplicate skip --config-file config.ini

# Update existing website configurations in target
uv run cli.py website-configs --on-duplicate update --config-file config.ini

# Use website configs from a local file instead of fetching from API
uv run cli.py website-configs --events-source file --events-file-path source_website_configs.json \
                              --target-token TOKEN --target-url URL

# Fetch website configs from API but save to a file for future use
uv run cli.py website-configs --events-source api --events-file-path my_website_configs.json \
                              --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL
```

> **Note:** Alert channel IDs are automatically remapped from source to target by matching channel names. Application, website, and mobile app smart alerts additionally remap their respective entity IDs. Alerts whose entity IDs cannot be found in the target are skipped with a warning.

---

### Configuration File Format

Create a configuration file (e.g., `config.ini`) with the following format:

```ini
[source]
token = YOUR_SOURCE_TOKEN
url = https://source-backend.example.com

[target]
token = YOUR_TARGET_TOKEN
url = https://target-backend.example.com

[general]
verify_ssl = true
events_source = api  # Use 'api' to fetch from API or 'file' to read from local file
events_file_path = source_events.json  # Path to read/write events JSON file
dry_run = false  # Set to true to preview changes without writing anything
```

### Environment Variables

You can also configure the tool using environment variables:

- `EVENTS_MIGRATOR_SOURCE_TOKEN`: API token for source backend
- `EVENTS_MIGRATOR_SOURCE_URL`: URL for source backend
- `EVENTS_MIGRATOR_TARGET_TOKEN`: API token for target backend
- `EVENTS_MIGRATOR_TARGET_URL`: URL for target backend
- `EVENTS_MIGRATOR_VERIFY_SSL`: Set to "false" to disable SSL verification
- `EVENTS_MIGRATOR_EVENTS_SOURCE`: Set to "api" or "file" to specify events source
- `EVENTS_MIGRATOR_EVENTS_FILE_PATH`: Path to the events JSON file
- `EVENTS_MIGRATOR_DRY_RUN`: Set to "true" to preview changes without writing anything

## Configuration Priority

The tool uses the following priority order for configuration (highest to lowest):

1. **Environment variables**
2. **Command line arguments**
3. **Configuration file**
4. **Built-in defaults**

## Project Structure

```
configuration-migration/
├── cli.py                                # Unified CLI entry point
├── config.py                             # Config class (file, env, CLI loading)
├── permissions.py                        # Permission checks and dry-run helpers
├── utils.py                              # Shared utilities (MigrationResult, prompt_duplicate, print_dry_run_preview, build_api)
├── base_smart_alerts_migrator.py         # Base class for all four smart alert migrators
├── config.ini                            # Example configuration file
├── requirements.txt                      # Python dependencies
├── run_tests.py                          # Test runner with coverage reporting
├── setup.py                              # Package setup
│
├── alert-channels/
│   └── migrator.py
├── alert-configs/
│   └── migrator.py
├── application-configuration/
│   └── migrator.py
├── application-smart-alerts/
│   └── migrator.py
├── custom-dashboards/
│   ├── migrator.py                       # Sync migrator (uses async_client internally)
│   ├── migrator_async.py                 # Async-first implementation
│   ├── async_client.py                   # aiohttp client with retry + connection pooling
│   └── rate_limiter.py                   # Token-bucket rate limiter for async requests
├── custom-events-specification/
│   └── migrator.py
├── endpoint-configuration/
│   └── migrator.py
├── infrastructure-smart-alerts/
│   └── migrator.py
├── maintenance-configs/
│   ├── migrator.py
│   └── README.md
├── mobile-app-configs/
├── mobile-app-smart-alerts/
│   └── migrator.py
├── service-configuration/
│   └── migrator.py
├── website-configs/
│   └── migrator.py
├── website-smart-alerts/
│   └── migrator.py
│
└── tests/
    ├── conftest.py                               # Shared fixtures, auto-mock for permissions
    ├── test_config.py                            # EventsMigrator integration tests
    ├── test_config_class.py                      # Config class unit tests
    ├── test_cli.py                               # CLI argument parsing and dispatch
    ├── test_utils.py                             # utils.py unit tests
    ├── test_permissions.py                       # permissions.py unit tests
    ├── test_events_migrator.py                   # Custom events migrator
    ├── test_alert_channels_migrator.py           # Alert channels migrator
    ├── test_alert_configs_migrator.py            # Alert configurations migrator
    ├── test_application_configs_migrator.py      # Application configurations migrator
    ├── test_service_configs_migrator.py          # Service configurations migrator
    ├── test_endpoint_configs_migrator.py         # Endpoint configurations migrator
    ├── test_custom_dashboards_migrator.py        # Custom dashboards migrator (sync)
    ├── test_custom_dashboards_migrator_async.py  # Custom dashboards migrator (async)
    ├── test_maintenance_configs_migrator.py      # Maintenance configurations migrator
    ├── test_website_configs_migrator.py          # Website configurations migrator
    ├── test_base_smart_alerts_migrator.py        # Base smart alerts migrator
    ├── test_infrastructure_smart_alerts_migrator.py
    ├── test_smart_alerts_dry_run.py              # Dry-run for all four smart alert types
    ├── test_rate_limiter_and_async_client.py     # Async infrastructure tests
    └── test_permissions.py                       # Already listed above
```

## Features

### File-Based Source

Any subcommand can read from a local JSON file instead of the source API. This is useful when you have already exported data, want to work offline, or need to edit the source before migrating.

```bash
# Use a local file as the source (no source credentials needed)
uv run cli.py events \
  --events-source file \
  --events-file-path my_events.json \
  --target-token TOKEN --target-url URL
```

#### Example JSON formats

**Custom Events:**
```json
[
  {
    "id": "yp2mpekXVcBc9V-e",
    "name": "CPU Usage Alert",
    "entityType": "host",
    "query": "entity.zone:production",
    "triggering": false,
    "description": "Alert when CPU usage is high",
    "expirationTime": 5000,
    "enabled": true,
    "rules": [
      {
        "ruleType": "threshold",
        "metricName": "cpu.used",
        "metricPattern": null,
        "rollup": 0,
        "window": 1000,
        "aggregation": "avg",
        "conditionOperator": ">=",
        "conditionValue": 80.0,
        "severity": 5
      }
    ],
    "ruleLogicalOperator": "AND"
  }
]
```

#### Example Alert Channels JSON file format:
```json
[
  {
    "emails": [
      "example@email.com"
    ],
    "kind": "EMAIL",
    "name": "Email Alert Channel",
    "customEmailSubjectPrefix": null,
    "id": "F6d30KPC4-n6LjGU"
  },
  {
    "kind": "SLACK",
    "name": "Slack Alert Channel",
    "channel": "alerts",
    "iconUrl": "https://www.example.com/media/instana.png",
    "emojiRendering": false,
    "webhookUrl": "https://hooks.slack.com/services/XXXXXXXXX/YYYYYYYYY/ZZZZZZZZZZZZZZZZZZZZZZZZ",
    "id": "apyYFfO5cLu_o7iy"
  }
]
```

#### Example Alert Configurations JSON file format:
```json
[
  {
    "id": "alert-config-1",
    "alertName": "High CPU Usage",
    "eventFilteringConfiguration": {
      "query": "entity.zone:production",
      "ruleIds": [],
      "eventTypes": [],
      "applicationAlertConfigIds": [],
      "validVersion": 1
    },
    "customPayloadFields": [],
    "integrationIds": [],
    "muteUntil": 0,
    "includeEntityNameInLegacyAlerts": false
  }
]
```

#### Example Website Configurations JSON file format:
```json
[
  {
    "id": "website-config-1",
    "name": "Production Web App"
  },
  {
    "id": "website-config-2",
    "name": "Customer Portal"
  }
]
```

## Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/instana/automation-with-apis.git
cd automation-with-apis/configuration-migration

# Install development dependencies
uv sync --dev

# Run tests with coverage
uv run python run_tests.py

# Run linting
uv run ruff check .

# Run formatting
uv run ruff format .
```

### Adding New Migrators

The tool is designed to be easily extensible. To add a new resource type:

1. **Create a new directory** in `configuration-migration/`
2. **Implement the migrator** following the existing pattern
3. **Add CLI integration** in `cli.py`
4. **Update documentation** and examples


## Testing

### Test Suite Overview

- **87% code coverage** across all source modules
- **565+ tests** across 19 test files, all passing
- All external HTTP calls are mocked — no live Instana instance required

### Running Tests

```bash
# Run the full suite with coverage report
uv run python run_tests.py

# Run a specific test file
uv run pytest tests/test_config_class.py -v

# Run a single test
uv run pytest tests/test_config_class.py::TestConfigValidate::test_missing_source_token_raises -v

# Run the full suite directly via pytest (with coverage)
uv run pytest tests/ --cov=. --cov-report=term-missing

# Generate an HTML coverage report
uv run pytest tests/ --cov=. --cov-report=html:htmlcov
```

### Test Structure

#### Test Files

| File | What it covers |
|---|---|
| `test_config_class.py` | `Config` class — defaults, `from_args()`, `load_from_file()`, `load_from_env()`, `validate()`, headers |
| `test_config.py` | `EventsMigrator` integration tests |
| `test_cli.py` | CLI argument parsing and subcommand dispatch |
| `test_utils.py` | `MigrationResult` helpers, `prompt_duplicate()`, `print_dry_run_preview()`, `print_api_error()`, `build_api()` |
| `test_permissions.py` | `check_destination_permissions()`, `check_permissions()`, `dry_run_connectivity_check()` |
| `test_events_migrator.py` | Custom events migrator |
| `test_alert_channels_migrator.py` | Alert channels migrator |
| `test_alert_configs_migrator.py` | Alert configurations migrator |
| `test_application_configs_migrator.py` | Application configurations migrator |
| `test_service_configs_migrator.py` | Service configurations migrator |
| `test_endpoint_configs_migrator.py` | Endpoint configurations migrator |
| `test_custom_dashboards_migrator.py` | Custom dashboards migrator (sync) |
| `test_custom_dashboards_migrator_async.py` | Custom dashboards migrator (async) |
| `test_maintenance_configs_migrator.py` | Maintenance configurations migrator |
| `test_website_configs_migrator.py` | Website configurations migrator |
| `test_base_smart_alerts_migrator.py` | `BaseSmartAlertsMigrator` shared logic |
| `test_infrastructure_smart_alerts_migrator.py` | Infrastructure smart alerts migrator |
| `test_smart_alerts_dry_run.py` | Dry-run for all four smart alert types + CLI flag tests |
| `test_rate_limiter_and_async_client.py` | `RateLimiter` and `AsyncHTTPClient` |

#### Test Categories

**Configuration** (`test_config_class.py`) — default values, file loading, environment variable overrides, validation error paths, header generation, CLI argument precedence.

**Migrator tests** — source and target data retrieval, creation, update, duplicate handling, error cases, dry-run preview output.

**CLI tests** (`test_cli.py`) — subcommand parsing, config wiring, exit codes.

**Shared infrastructure** (`test_utils.py`, `test_permissions.py`) — `MigrationResult` helpers, interactive duplicate prompt, dry-run preview formatter, permission check, connectivity check abort paths.

### Test Dependencies

- `pytest` — test framework
- `pytest-cov` — coverage reporting
- `pytest-mock` — `mocker` fixture
- `unittest.mock` — `@patch`, `MagicMock`, `AsyncMock`
- `aiohttp`, `aiohttp-retry` — required for async dashboard tests

### Writing New Tests

1. Name files `test_<module>.py`, test methods `test_<method>_<scenario>`
2. Mock all external HTTP calls with `@patch`
3. Use the `sample_config` fixture from `conftest.py` for a ready-made `MagicMock` config
4. Test both the happy path and failure paths (network errors, missing permissions, invalid data)

```python
import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import Config

class TestMyMigrator:
    def setup_method(self):
        self.config = Config()
        self.config.source_token = "src-tok"
        self.config.source_url = "http://source.example.com"
        self.config.target_token = "tgt-tok"
        self.config.target_url = "http://target.example.com"

    @patch('migrator.requests.get')
    def test_fetch_source_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"id": "1", "name": "test"}]
        # assert ...
```

## License

This project is licensed under the Apache-2.0 license.

