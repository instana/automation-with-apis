# Instana Configuration Migration Tool

A comprehensive, enterprise-grade tool for migrating Instana configurations between different environments, instances, and organizations. This tool streamlines the process of moving custom events, alert channels, alert configurations, and other Instana resources across your infrastructure.

## Overview

The Instana Configuration Migration Tool is designed to solve real-world challenges faced by DevOps teams, SREs, and platform engineers who need to:

- **Standardize configurations** across multiple Instana environments (dev, staging, production)
- **Migrate configurations** when upgrading Instana versions or moving between instances
- **Replicate successful configurations** from one environment to another
- **Backup and restore** critical monitoring configurations
- **Comply with infrastructure-as-code** practices for monitoring configurations

## Supported Resources

### 1. Custom Event Specifications
- **Event rules** and conditions
- **Metric patterns** and thresholds
- **Severity levels** and expiration times
- **Entity type filtering**

### 2. Alert Channels
- **Email notifications** with custom subjects
- **Slack integrations** with webhooks
- **Webhook endpoints** for custom integrations
- **PagerDuty** and other incident management tools

### 3. Alert Configurations
- **Alert rules** and conditions
- **Threshold configurations** and operators
- **Time windows** and evaluation periods
- **Integration mappings** to alert channels

## Installation

### Prerequisites
- **Python 3.9+** (as declared in `pyproject.toml`)
- **uv** package manager (recommended) or pip
- **Instana API tokens** for both backends, with the right permissions —
  see [API Token Permissions](#api-token-permissions). This is the most
  common cause of a failed first run.
- **Network connectivity** to both Instana instances. If either is only
  reachable over a VPN, connect first: an unreachable host surfaces as a
  connection error rather than an obvious DNS failure.

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/instana/automation-with-apis.git
cd automation-with-apis/configuration-migration

# Install dependencies using uv
uv sync

# Create your configuration from the template
cp config.ini.example config.ini
# then edit config.ini and fill in both tokens and URLs
```

### Using pip (Alternative)

```bash
# Clone the repository
git clone https://github.com/instana/automation-with-apis.git
cd automation-with-apis/configuration-migration

# Install dependencies
pip install -r requirements.txt

# Create your configuration from the template
cp config.ini.example config.ini
```

### Verifying Your Setup

Before running a migration against real data, confirm the CLI loads and
that both backends accept your tokens.

```bash
# 1. The CLI and its subcommands are available
uv run cli.py --help

# 2. Your tokens and URLs actually work. Replace the URL and token with
#    your own; 200 means success, 401 means a bad token, 403 means the
#    token is valid but lacks a required permission, and a connection
#    error usually means a missing port or no VPN.
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: apiToken YOUR_TOKEN" \
  "https://your-backend.example.com/api/events/settings/alertingChannels"
```

Add `-k` to that `curl` if the backend uses a self-signed certificate,
and set `verify_ssl = false` in `config.ini` for the same reason.

### Running Without Installation

You can run the tool directly from the source code:

```bash
# Install minimal dependencies
uv add requests urllib3 configparser

# Run directly
uv run configuration-migration/cli.py events --help
```

## API Token Permissions

Create tokens under **Settings > API Tokens** in each Instana UI. The
permission each migrator needs is listed below, taken from Instana's
published API specification.

| Migrator | Source token needs | Target token needs |
|----------|--------------------|--------------------|
| `events` | Can configure custom alerts | Can configure custom alerts |
| `channels` | Can configure integrations | Can configure integrations |
| `configs` | Can configure custom alerts | Can configure custom alerts |
| `custom-dashboards` | Default, plus *Can configure users* for owner mapping | Default; *Create public custom dashboards* if dashboards are shared |

The **source token only ever reads** and the **target token writes**, so
using a read-only source token is a good way to make it impossible to
modify the backend you are copying from by mistake.

### Why a token can list items but still fail

Instana does not gate every endpoint behind the same permission, and some
**read** endpoints require a permission whose name sounds write-only. The
practical effect is that a partially-permissioned token lists resources
successfully and then returns `403` when the migrator reaches for their
details, which looks like a bug in the tool but is not.

If you see `403 Client Error: Forbidden` on some endpoints while others
return data, the token is valid but missing a permission. Compare the
failing URL against the table above.

Some permissions cannot be granted by a user who does not already hold
them, and on a shared instance they may not appear on the token creation
screen at all. In that case an administrator for that instance has to
either raise your role or create the token for you.

## Usage

### Command Line Interface

The tool provides a unified CLI with multiple subcommands for different resource types:

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

### Configuration File Format

Copy the template and edit it, rather than writing the file from scratch:

```bash
cp config.ini.example config.ini
```

`config.ini.example` documents every available key. The minimum you need:

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
```

`config.ini` is gitignored, so your tokens are not committed.

Two details that account for most first-run failures:

**Include the port if the backend uses a non-default one.** Hosted
instances are served over HTTPS on port 443, so a bare hostname works.
A locally running instance usually listens elsewhere, and the port has to
be part of the URL or every request fails to connect:

```ini
url = https://local-instana.example.com:4000
```

**Set `verify_ssl = false` for self-signed certificates.** Local
development instances typically use one. Left as `true`, the run fails
partway through with:

```
SSLError: certificate verify failed: self-signed certificate
```

This is TLS verification working as intended, not a defect in the tool.
Note that `verify_ssl` is a single global switch covering both backends,
so disabling it for a local target also disables it for the source.

### Environment Variables

You can also configure the tool using environment variables:

- `EVENTS_MIGRATOR_SOURCE_TOKEN`: API token for source backend
- `EVENTS_MIGRATOR_SOURCE_URL`: URL for source backend
- `EVENTS_MIGRATOR_TARGET_TOKEN`: API token for target backend
- `EVENTS_MIGRATOR_TARGET_URL`: URL for target backend
- `EVENTS_MIGRATOR_VERIFY_SSL`: Set to "false" to disable SSL verification
- `EVENTS_MIGRATOR_EVENTS_SOURCE`: Set to "api" or "file" to specify events source
- `EVENTS_MIGRATOR_EVENTS_FILE_PATH`: Path to the events JSON file

## Configuration Priority

The tool uses the following priority order for configuration (highest to lowest):

1. **Environment variables**
2. **Command line arguments**
3. **Configuration file**

## Exit Codes

Every migrator exits `0` only when it changed something — specifically
when `migrated > 0` or `updated > 0` — and `1` otherwise.

**A successful run that had nothing to do therefore exits `1`.** Migrate
the same configuration twice and the second run exits `1`, because
everything already existed and was skipped. Exit `1` means "nothing
changed", not "something broke".

This matters if you wire the tool into CI or a shell script with
`set -e`, where a second run would look like a failure. To distinguish a
genuine problem from a no-op, read the summary line the migrator prints
rather than relying on the exit code alone:

```
Migration complete. Found 12 source items, migrated 0, updated 0, skipped 12
```

## Project Structure

```
configuration-migration/
├── config.py                    # Common configuration for all migrators
├── cli.py                       # Unified CLI for all migrators
├── config.ini                   # Common configuration file
├── requirements.txt             # Python dependencies
├── setup.py                     # Package setup
├── MANIFEST.in                  # Package manifest
├── source_events.json           # Sample custom events data
├── sample_alert_channels.json   # Sample alert channels data
├── sample_alert_configs.json    # Sample alert configurations data
├── custom-events-specification/
│   └── migrator.py              # Custom events migrator
├── alert-channels/
│   └── migrator.py              # Alert channels migrator
└── alert-configs/
    └── migrator.py              # Alert configurations migrator
```

## Features

### File-Based Source

You can now use a local JSON file as the source for custom events or alert channels instead of fetching them from an API:

1. **Reading from file**: Use the `--events-source file` option to read from a local file.
2. **Automatic file saving**: When fetching from the API, data is automatically saved to the file specified by `--events-file-path`.

#### Example Custom Events JSON file format:
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

Around 99 unit tests cover configuration handling and each migrator, with
external HTTP calls mocked throughout so the suite needs no Instana
access and makes no network requests.

### Running Tests

Use `run_tests.py`. It is the **only** supported way to run the whole
suite:

```bash
uv run python run_tests.py
```

> **`pytest tests/` does not work, and this is expected.** Every migrator
> lives in a module named `migrator.py` in a differently-named directory.
> Python caches the first `migrator` it imports, so collecting them all in
> one process makes later test files resolve to the wrong module and fail
> with `ImportError` or `AttributeError`. `run_tests.py` works around this
> by running each test file in its own subprocess.

To run one file at a time, that is fine — the collision only happens when
several are collected together:

```bash
uv run pytest tests/test_config.py -v
uv run pytest tests/test_events_migrator.py::TestEventsMigrator -v
```

### Known Test Failures

The suite does **not** currently pass cleanly. If you see these on a
fresh checkout, you have not broken anything:

| File | Failing | Cause |
|------|---------|-------|
| `tests/test_cli.py` | 7 of 7 | Patches `cli.EventsMigrator`, but `cli.py` imports migrators *inside* each dispatch branch, so there is no module attribute to patch. Excluded from `run_tests.py`, so it normally goes unnoticed. |
| `tests/test_config.py` | 2 of 12 | Hand-built `MockArgs` fixtures predate the performance-tuning arguments added to `Config.from_args`, so they lack `max_concurrent` and raise `AttributeError`. |

Both are stale-test problems rather than defects in the code under test.
Fixing them is a good first contribution.

### Coverage

Coverage is only meaningfully measured for `config.py`. The migrator
modules cannot be imported together in one process (see above), which is
also why a single combined coverage report across all of them is not
currently produced.

```bash
uv run pytest tests/test_config.py --cov=config --cov-report=term-missing
```

### Test Structure

#### Test Files
```
tests/
├── test_config.py              # Configuration management tests
├── test_events_migrator.py     # Custom events migrator tests
├── test_alert_channels_migrator.py  # Alert channels migrator tests
├── test_alert_configs_migrator.py   # Alert configs migrator tests
├── test_cli.py                 # CLI interface tests
├── conftest.py                 # Shared test fixtures
└── __init__.py                 # Package initialization
```

#### Test Categories

##### Configuration Tests (`test_config.py`)
- ✅ Default value initialization
- ✅ Configuration loading from files
- ✅ Environment variable handling
- ✅ Header generation for API requests
- ✅ Validation logic for required fields
- ✅ Error handling for missing credentials

##### Migrator Tests
- ✅ Initialization and setup
- ✅ Source data retrieval (file and API)
- ✅ Target data retrieval
- ✅ Data creation and update operations
- ✅ Error handling and edge cases

##### CLI Tests (`test_cli.py`)
- ✅ Command-line argument parsing
- ✅ Subcommand execution
- ✅ Error handling for invalid commands

### Test Dependencies

The test suite uses the following testing tools:
- **pytest**: Test framework and runner
- **pytest-cov**: Coverage reporting
- **unittest.mock**: Mocking external dependencies
- **requests**: HTTP request mocking

### Development Testing

#### Running Individual Tests
```bash
# Run specific test file
uv run pytest tests/test_config.py

# Run specific test method
uv run pytest tests/test_config.py::TestConfig::test_init_default_values

# Run with verbose output
uv run pytest tests/test_config.py -v
```

#### Coverage Analysis
```bash
# Generate coverage report
uv run pytest tests/test_config.py --cov=config --cov-report=term-missing

# Generate HTML coverage report
uv run pytest tests/test_config.py --cov=config --cov-report=html:htmlcov
```

### Test Best Practices

#### Writing New Tests
1. **Follow naming convention**: `test_<module_name>.py`
2. **Use descriptive test names**: `test_<method>_<scenario>`
3. **Mock external dependencies**: Use `@patch` decorators
4. **Test both success and failure cases**
5. **Validate error messages and edge cases**

#### Example Test Structure
```python
import pytest
from unittest.mock import patch, MagicMock
from config import Config

class TestConfig:
    def test_init_default_values(self):
        """Test default value initialization."""
        config = Config()
        assert config.source_token is None
        assert config.source_url is None
    
    @patch('config.requests.get')
    def test_api_call_success(self, mock_get):
        """Test successful API call."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": "test"}
        # Test implementation
```

### Known Limitations

#### Import Path Issues

Every migrator module is named `migrator.py`, so only one can be imported
per Python process. This is why `run_tests.py` runs each test file in a
subprocess, and why combined coverage across migrators is not produced.
Individual test files run correctly.

## Troubleshooting

### `SSLCertVerificationError: self-signed certificate`

The backend presents a self-signed certificate, which local development
instances normally do. Set `verify_ssl = false` in `config.ini`, or pass
`--no-verify-ssl`. This affects both backends, not just the one that
needs it.

### The run aborts with a connection error, or `curl` returns `000`

Usually one of:

- **The URL is missing a port.** Local instances often listen on
  something other than 443, and the port must be in the URL.
- **You are not on the VPN**, if the instance is internal only.
- **The host does not resolve.** Some local instances are reachable only
  through an `/etc/hosts` entry, which means the name resolves on the
  machine running the instance but not necessarily from yours.

### `401 Client Error: Unauthorized`

The token is wrong, expired, or was created on the other backend. Tokens
are per-instance and are not interchangeable.

### `403 Client Error: Forbidden` on some endpoints but not others

The token is valid but lacks a permission. Because Instana gates
endpoints individually, a partially-permissioned token can list resources
and then fail when fetching their details. See
[API Token Permissions](#api-token-permissions). Nothing about your
network or config file is wrong in this case.

### `400 ... name already used` when creating something

An item with that name already exists in the target backend. Instana's
uniqueness checks ignore differences in capitalisation and surrounding
whitespace, so two names that look different to you can still collide.

### `While reading from 'config.ini': section 'source' already exists`

`config.ini` contains a duplicated `[source]` or `[target]` block. This
is easy to cause by pasting a multi-line shell command such as a heredoc
into an editor, or by appending to the file twice. Start again from the
template:

```bash
cp config.ini.example config.ini
```

### The migration exits `1` but the output looks fine

Expected when nothing needed changing. See [Exit Codes](#exit-codes).

### `pytest tests/` fails to collect

Expected. Use `uv run python run_tests.py`. See
[Running Tests](#running-tests).

### `ImportError: cannot import name ...Migrator from 'migrator'`

Two migrator modules were imported in the same process. Run the test file
on its own, or use `run_tests.py`.

## License

This project is licensed under the Apache-2.0 license.

