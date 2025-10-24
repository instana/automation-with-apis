# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial open source release
- Comprehensive documentation and contributing guidelines
- Modern Python project configuration with pyproject.toml
- Development tools configuration (Ruff, Black, MyPy, Pytest)

### Changed
- Switched from pip to uv for better dependency management
- Updated all documentation to use `uv run` instead of `python`
- Enhanced README with comprehensive overview and background
- Improved project structure and organization

## [1.0.0] - 2024-01-XX

### Added
- **Custom Events Migration**: Migrate custom event specifications between Instana backends
- **Alert Channels Migration**: Migrate alert channels (email, Slack, webhooks) between environments
- **Alert Configurations Migration**: Migrate alert configurations and rules between instances
- **Unified CLI Interface**: Single command-line tool for all migration types
- **File-based Source Support**: Import configurations from local JSON files
- **Interactive Duplicate Handling**: Choose to skip, update, or cancel for existing items
- **SSL Verification**: Configurable SSL certificate verification
- **Environment Variable Support**: Configure via environment variables
- **Comprehensive Error Handling**: Detailed error messages and recovery options

### Features
- **Multiple Source Types**: API endpoints or local JSON files
- **Flexible Configuration**: Command line arguments, config files, or environment variables
- **Batch Operations**: Migrate multiple resources in single commands
- **Audit Trail**: Track migration progress and results
- **Rollback Support**: Easy restoration of previous configurations

### Technical Details
- **Python 3.8+ Support**: Modern Python compatibility
- **REST API Integration**: Direct integration with Instana APIs
- **Modular Architecture**: Extensible design for new resource types
- **Type Safety**: Comprehensive type hints throughout
- **Error Recovery**: Graceful handling of network and API errors

## [0.9.0] - 2024-01-XX

### Added
- Initial beta release with core migration functionality
- Basic CLI interface for custom events migration
- Configuration file support
- Basic error handling and logging

### Changed
- Experimental features and rapid development
- Breaking changes between releases

---

## Version History

- **1.0.0**: First stable release with comprehensive migration capabilities
- **0.9.0**: Beta release with core functionality

## Migration Guide

### From 0.9.0 to 1.0.0

- **Breaking Changes**: None - this is a stable release
- **New Features**: All features from beta are now stable
- **Deprecations**: None
- **Configuration**: No changes required

## Contributing

To add entries to this changelog:

1. **Follow the format** above
2. **Use present tense** ("Add" not "Added")
3. **Group changes** by type (Added, Changed, Deprecated, Removed, Fixed, Security)
4. **Reference issues** when applicable
5. **Update version** and date for releases

## Release Process

1. **Update version** in pyproject.toml
2. **Update changelog** with new version
3. **Create git tag** for the release
4. **Update release notes** on GitHub
5. **Publish to PyPI** (when applicable)
