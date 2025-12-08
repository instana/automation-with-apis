# Instana Configuration Migration Tool

A comprehensive, enterprise-grade tool for migrating Instana configurations between different environments, instances, and organizations. This tool streamlines the process of moving custom events, alert channels, alert configurations, and other Instana resources across your infrastructure.

## 🌟 Overview

The Instana Configuration Migration Tool is designed to solve real-world challenges faced by DevOps teams, SREs, and platform engineers who need to:

- **Standardize configurations** across multiple Instana environments (dev, staging, production)
- **Migrate configurations** when upgrading Instana versions or moving between instances
- **Replicate successful configurations** from one environment to another
- **Backup and restore** critical monitoring configurations
- **Comply with infrastructure-as-code** practices for monitoring configurations

## 🎯 Background & Problem Statement

### The Challenge

Modern organizations often operate multiple Instana environments for different purposes:
- **Development/Testing**: For validating monitoring configurations
- **Staging**: For pre-production testing and validation
- **Production**: For live monitoring and alerting
- **Disaster Recovery**: For business continuity
- **Multi-region**: For global application monitoring

Managing configurations across these environments manually is:
- **Error-prone**: Copy-paste errors, missing configurations
- **Time-consuming**: Hours of manual work for each migration
- **Inconsistent**: Different configurations across environments
- **Risky**: Potential downtime due to misconfigured monitoring
- **Non-compliant**: Difficult to audit and track changes

### The Solution

This tool provides a **unified, automated approach** to Instana configuration management that:
- **Eliminates manual errors** through programmatic migration
- **Reduces migration time** from hours to minutes
- **Ensures consistency** across all environments
- **Provides audit trails** for compliance requirements
- **Supports both API and file-based** migration strategies

## 🚀 Key Benefits

### For DevOps Teams
- **Automated Migration**: Reduce manual configuration time by 90%
- **Error Reduction**: Eliminate copy-paste and configuration errors
- **Environment Parity**: Ensure identical configurations across environments
- **Rollback Capability**: Easy restoration of previous configurations

### For SREs
- **Monitoring Reliability**: Consistent alerting and monitoring across environments
- **Incident Prevention**: Reduce false positives/negatives through standardized configurations
- **Operational Efficiency**: Faster environment setup and configuration updates
- **Compliance**: Maintain audit trails for configuration changes

### For Platform Engineers
- **Infrastructure as Code**: Version control your monitoring configurations
- **Standardization**: Enforce consistent monitoring patterns across teams
- **Scalability**: Manage hundreds of configurations efficiently
- **Integration**: Easily integrate with CI/CD pipelines

## 🏗️ Architecture & Design Principles

### Modular Design
- **Separate migrators** for different resource types
- **Common configuration** management across all migrators
- **Unified CLI interface** for consistent user experience
- **Extensible architecture** for adding new resource types

### Security First
- **Token-based authentication** for secure API access
- **SSL verification** by default (configurable)
- **Environment variable support** for sensitive credentials
- **No credential storage** in code or logs

### Flexibility
- **Multiple source types**: API endpoints or local JSON files
- **Configurable targets**: Any Instana instance with proper credentials
- **Customizable behavior**: Skip, update, or create new resources
- **Batch operations**: Migrate multiple resources in one command

## 📋 Supported Resources

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

### 4. Custom Dashboards
- **Dashboard widgets** and configurations
- **User permissions** and sharing settings
- **Timezone and time window** settings
- **Chart and graph** configurations

## 🛠️ Installation

### Prerequisites
- **Python 3.8+** (3.9+ recommended)
- **uv** package manager (recommended) or pip
- **Instana access** with API tokens
- **Network connectivity** to Instana instances

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/instana-configuration-migration.git
cd instana-configuration-migration

# Install dependencies using uv
uv sync

# Verify installation
uv run python --version
```

### Using pip (Alternative)

```bash
# Clone the repository
git clone https://github.com/your-org/instana-configuration-migration.git
cd instana-configuration-migration

# Install dependencies
pip install -r requirements.txt

# Verify installation
python --version
```

### Running Without Installation

You can run the tool directly from the source code:

```bash
# Install minimal dependencies
uv add requests urllib3 configparser

# Run directly
uv run configuration-migration/cli.py events --help
```

## 📖 Usage

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

#### Custom Dashboards Migration

```bash
# Basic usage with command line arguments
uv run cli.py custom-dashboards --source-token YOUR_SOURCE_TOKEN --source-url https://source-backend.example.com  \
                               --target-token YOUR_TARGET_TOKEN --target-url https://target-backend.example.com --default-owner-id dummy_owner_id

# Using a configuration file
uv run cli.py custom-dashboards --config-file config.ini --default-owner-id dummy_owner_id --on-duplicate skip

# Disable SSL verification (not recommended for production)
uv run cli.py custom-dashboards --no-verify-ssl --source-token TOKEN --source-url URL --target-token TOKEN --target-url URL --default-owner-id dummy_owner_id
```

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

## ⚙️ Configuration Priority

The tool uses the following priority order for configuration (highest to lowest):

1. **Environment variables**
2. **Command line arguments**
3. **Configuration file**

## 🏛️ Project Structure

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
└── custom-dashboards/
    └── migrator.py              # Custom dashboards migrator
```

## ✨ Features

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
    "webhookUrl": "https://hooks.slack.com/services/XXXX/YYYY/ZZZZ",
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

## 🔧 Development

### Setting Up Development Environment

```bash
# Clone the repository
git clone https://github.com/your-org/instana-configuration-migration.git
cd instana-configuration-migration

# Install development dependencies
uv sync --dev

# Run tests
uv run pytest

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

### Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## 🚨 Troubleshooting

### Common Issues

#### Authentication Errors
- **401 Unauthorized**: Check your API tokens and ensure they're valid
- **403 Forbidden**: Verify your tokens have the necessary permissions
- **Token expiration**: Refresh your API tokens if they've expired

#### Network Issues
- **Connection timeout**: Check network connectivity and firewall rules
- **SSL errors**: Verify SSL certificates or use `--no-verify-ssl` (not recommended for production)
- **Proxy issues**: Configure proxy settings if required by your network

#### Data Format Issues
- **422 Unprocessable Entity**: Check that your data format matches the expected schema
- **Missing required fields**: Ensure all required fields are present in your data
- **Invalid field values**: Verify field values are within acceptable ranges

### Getting Help

- **Documentation**: Check this README and the individual migrator documentation
- **Issues**: Report bugs and request features on GitHub
- **Discussions**: Join community discussions for help and best practices

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Support

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For community support and questions
- **Documentation**: Comprehensive guides and examples
- **Examples**: Sample configurations and use cases

## 🙏 Acknowledgments

- **Instana Team**: For the excellent monitoring platform and API
- **Open Source Community**: For the tools and libraries that make this possible
- **Contributors**: Everyone who has helped improve this tool

---

**Made with ❤️ for the DevOps and SRE community**
