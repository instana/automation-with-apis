"""Command-line interface for Custom Events, Alert Channels, Alert Configurations, Custom Dashboards, and Website Configs Migrator."""

import os
import sys
import argparse
from config import Config

# Import will be done conditionally based on command


def main():
    """Main entry point for the command-line interface."""
    try:
        # Create argument parser for the main command
        parser = argparse.ArgumentParser(
            description="Migrate custom events, alert channels, and alert configurations between Instana backends"
        )
        
        # Add subcommand for different migrators
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Custom events migrator
        events_parser = subparsers.add_parser('events', help='Migrate custom events')
        events_parser.add_argument('--config-file', help='Path to configuration file')
        events_parser.add_argument('--source-token', help='API token for source backend')
        events_parser.add_argument('--source-url', help='URL for source backend')
        events_parser.add_argument('--target-token', help='API token for target backend')
        events_parser.add_argument('--target-url', help='URL for target backend')
        events_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        events_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for custom events (api or file)')
        events_parser.add_argument('--events-file-path', default='source_events.json', help='Path to the source events JSON file (default: source_events.json)')
        events_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate event is found (default: ask)')
        events_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')
        
        # Alert channels migrator
        channels_parser = subparsers.add_parser('channels', help='Migrate alert channels')
        channels_parser.add_argument('--config-file', help='Path to configuration file')
        channels_parser.add_argument('--source-token', help='API token for source backend')
        channels_parser.add_argument('--source-url', help='URL for source backend')
        channels_parser.add_argument('--target-token', help='API token for target backend')
        channels_parser.add_argument('--target-url', help='URL for target backend')
        channels_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        channels_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for alert channels (api or file)')
        channels_parser.add_argument('--events-file-path', default='source_channels.json', help='Path to the source channels JSON file (default: source_channels.json)')
        channels_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate alert channel is found (default: ask)')
        channels_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')
        
        # Alert configurations migrator
        configs_parser = subparsers.add_parser('configs', help='Migrate alert configurations')
        configs_parser.add_argument('--config-file', help='Path to configuration file')
        configs_parser.add_argument('--source-token', help='API token for source backend')
        configs_parser.add_argument('--source-url', help='URL for source backend')
        configs_parser.add_argument('--target-token', help='API token for target backend')
        configs_parser.add_argument('--target-url', help='URL for target backend')
        configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for alert configurations (api or file)')
        configs_parser.add_argument('--events-file-path', default='source_alert_configs.json', help='Path to the source alert configurations JSON file (default: source_alert_configs.json)')
        configs_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate alert configuration is found (default: ask)')
        configs_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Application configurations migrator
        applications_parser = subparsers.add_parser('applications', help='Migrate application configurations (Application Perspectives)')
        applications_parser.add_argument('--config-file', help='Path to configuration file')
        applications_parser.add_argument('--source-token', help='API token for source backend')
        applications_parser.add_argument('--source-url', help='URL for source backend')
        applications_parser.add_argument('--target-token', help='API token for target backend')
        applications_parser.add_argument('--target-url', help='URL for target backend')
        applications_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        applications_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for application configs (api or file)')
        applications_parser.add_argument('--events-file-path', default='source_applications.json', help='Path to the source application configs JSON file (default: source_applications.json)')
        applications_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate application config is found (default: ask)')
        applications_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Service configurations migrator
        services_parser = subparsers.add_parser('services', help='Migrate service configurations')
        services_parser.add_argument('--config-file', help='Path to configuration file')
        services_parser.add_argument('--source-token', help='API token for source backend')
        services_parser.add_argument('--source-url', help='URL for source backend')
        services_parser.add_argument('--target-token', help='API token for target backend')
        services_parser.add_argument('--target-url', help='URL for target backend')
        services_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        services_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for service configs (api or file)')
        services_parser.add_argument('--events-file-path', default='source_services.json', help='Path to the source service configs JSON file (default: source_services.json)')
        services_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate service config is found (default: ask)')
        services_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Endpoint configurations migrator
        endpoints_parser = subparsers.add_parser('endpoints', help='Migrate endpoint configurations')
        endpoints_parser.add_argument('--config-file', help='Path to configuration file')
        endpoints_parser.add_argument('--source-token', help='API token for source backend')
        endpoints_parser.add_argument('--source-url', help='URL for source backend')
        endpoints_parser.add_argument('--target-token', help='API token for target backend')
        endpoints_parser.add_argument('--target-url', help='URL for target backend')
        endpoints_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        endpoints_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for endpoint configs (api or file)')
        endpoints_parser.add_argument('--events-file-path', default='source_endpoints.json', help='Path to the source endpoint configs JSON file (default: source_endpoints.json)')
        endpoints_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate endpoint config is found (default: ask)')
        endpoints_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Custom dashboards migrator
        custom_dashboards_parser = subparsers.add_parser('custom-dashboards', help='Migrate custom dashboards')
        custom_dashboards_parser.add_argument('--config-file', help='Path to configuration file')
        custom_dashboards_parser.add_argument('--source-token', help='API token for source backend')
        custom_dashboards_parser.add_argument('--source-url', help='URL for source backend')
        custom_dashboards_parser.add_argument('--target-token', help='API token for target backend')
        custom_dashboards_parser.add_argument('--target-url', help='URL for target backend')
        custom_dashboards_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        custom_dashboards_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for dashboards (api or file)')
        custom_dashboards_parser.add_argument('--events-file-path', help='Path to the dashboards JSON file (when using file source)')
        custom_dashboards_parser.add_argument('--default-owner-id', help='Default owner ID for unmapped users')
        custom_dashboards_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate dashboard is found (default: ask)')
        custom_dashboards_parser.add_argument('--max-concurrent', type=int, help='Maximum concurrent API requests (default: 10)')
        custom_dashboards_parser.add_argument('--rate-limit', type=int, help='API requests per second limit (default: 50)')
        custom_dashboards_parser.add_argument('--request-timeout', type=int, help='Timeout per request in seconds (default: 30)')
        custom_dashboards_parser.add_argument('--retry-attempts', type=int, help='Number of retry attempts for failed requests (default: 3)')
        custom_dashboards_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Maintenance configurations migrator
        maintenance_parser = subparsers.add_parser('maintenance-configs', help='Migrate maintenance configurations')
        maintenance_parser.add_argument('--config-file', help='Path to configuration file')
        maintenance_parser.add_argument('--source-token', help='API token for source backend')
        maintenance_parser.add_argument('--source-url', help='URL for source backend')
        maintenance_parser.add_argument('--target-token', help='API token for target backend')
        maintenance_parser.add_argument('--target-url', help='URL for target backend')
        maintenance_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        maintenance_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for maintenance configurations (api or file)')
        maintenance_parser.add_argument('--events-file-path', default='source_maintenance_configs.json', help='Path to the maintenance configurations JSON file (default: source_maintenance_configs.json)')
        maintenance_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a maintenance configuration already exists in the target (default: ask)')
        maintenance_parser.add_argument('--request-timeout', type=int, help='Timeout per request in seconds (default: 30)')
        maintenance_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Application smart alerts migrator
        app_smart_alerts_parser = subparsers.add_parser('application-smart-alerts', help='Migrate application smart alert configurations')
        app_smart_alerts_parser.add_argument('--config-file', help='Path to configuration file')
        app_smart_alerts_parser.add_argument('--source-token', help='API token for source backend')
        app_smart_alerts_parser.add_argument('--source-url', help='URL for source backend')
        app_smart_alerts_parser.add_argument('--target-token', help='API token for target backend')
        app_smart_alerts_parser.add_argument('--target-url', help='URL for target backend')
        app_smart_alerts_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        app_smart_alerts_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for application smart alerts (api or file)')
        app_smart_alerts_parser.add_argument('--events-file-path', default='source_application_smart_alerts.json', help='Path to the source alert configs JSON file (default: source_application_smart_alerts.json)')
        app_smart_alerts_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate application smart alert is found (default: ask)')
        app_smart_alerts_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Website smart alerts migrator
        website_smart_alerts_parser = subparsers.add_parser('website-smart-alerts', help='Migrate website smart alert configurations')
        website_smart_alerts_parser.add_argument('--config-file', help='Path to configuration file')
        website_smart_alerts_parser.add_argument('--source-token', help='API token for source backend')
        website_smart_alerts_parser.add_argument('--source-url', help='URL for source backend')
        website_smart_alerts_parser.add_argument('--target-token', help='API token for target backend')
        website_smart_alerts_parser.add_argument('--target-url', help='URL for target backend')
        website_smart_alerts_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        website_smart_alerts_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for website smart alerts (api or file)')
        website_smart_alerts_parser.add_argument('--events-file-path', default='source_website_smart_alerts.json', help='Path to the source alert configs JSON file (default: source_website_smart_alerts.json)')
        website_smart_alerts_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate website smart alert is found (default: ask)')
        website_smart_alerts_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # mobile app smart alerts migrator
        mobile_app_smart_alerts_parser = subparsers.add_parser('mobile-app-smart-alerts', help='Migrate mobile app smart alert configurations')
        mobile_app_smart_alerts_parser.add_argument('--config-file', help='Path to configuration file')
        mobile_app_smart_alerts_parser.add_argument('--source-token', help='API token for source backend')
        mobile_app_smart_alerts_parser.add_argument('--source-url', help='URL for source backend')
        mobile_app_smart_alerts_parser.add_argument('--target-token', help='API token for target backend')
        mobile_app_smart_alerts_parser.add_argument('--target-url', help='URL for target backend')
        mobile_app_smart_alerts_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        mobile_app_smart_alerts_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for mobile app smart alerts (api or file)')
        mobile_app_smart_alerts_parser.add_argument('--events-file-path', default='source_mobile_app_smart_alerts.json', help='Path to the source alert configs JSON file (default: source_mobile_app_smart_alerts.json)')
        mobile_app_smart_alerts_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate mobile app smart alert is found (default: ask)')
        mobile_app_smart_alerts_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Infrastructure smart alerts migrator
        infra_smart_alerts_parser = subparsers.add_parser('infrastructure-smart-alerts', help='Migrate infrastructure smart alert configurations')
        infra_smart_alerts_parser.add_argument('--config-file', help='Path to configuration file')
        infra_smart_alerts_parser.add_argument('--source-token', help='API token for source backend')
        infra_smart_alerts_parser.add_argument('--source-url', help='URL for source backend')
        infra_smart_alerts_parser.add_argument('--target-token', help='API token for target backend')
        infra_smart_alerts_parser.add_argument('--target-url', help='URL for target backend')
        infra_smart_alerts_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        infra_smart_alerts_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for infrastructure smart alerts (api or file)')
        infra_smart_alerts_parser.add_argument('--events-file-path',  default='source_infrastructure_smart_alerts.json', help='Path to the source alert configs JSON file (default: source_ifrastructure_smart_alerts.json)')
        infra_smart_alerts_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate infrastructure alert config is found (default: ask)')
        infra_smart_alerts_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Website configs migrator
        website_configs_parser = subparsers.add_parser('website-configs', help='Migrate website monitoring configurations')
        website_configs_parser.add_argument('--config-file', help='Path to configuration file')
        website_configs_parser.add_argument('--source-token', help='API token for source backend')
        website_configs_parser.add_argument('--source-url', help='URL for source backend')
        website_configs_parser.add_argument('--target-token', help='API token for target backend')
        website_configs_parser.add_argument('--target-url', help='URL for target backend')
        website_configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        website_configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for website configs (api or file)')
        website_configs_parser.add_argument('--events-file-path', default='source_website_configs.json', help='Path to the website configs JSON file (default: source_website_configs.json)')
        website_configs_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate website is found (default: ask)')
        website_configs_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

         # Mobile app configs migrator
        mobile_app_configs_parser = subparsers.add_parser('mobile-app-configs', help='Migrate mobile app monitoring configurations')
        mobile_app_configs_parser.add_argument('--config-file', help='Path to configuration file')
        mobile_app_configs_parser.add_argument('--source-token', help='API token for source backend')
        mobile_app_configs_parser.add_argument('--source-url', help='URL for source backend')
        mobile_app_configs_parser.add_argument('--target-token', help='API token for target backend')
        mobile_app_configs_parser.add_argument('--target-url', help='URL for target backend')
        mobile_app_configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        mobile_app_configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for mobile app configs (api or file)')
        mobile_app_configs_parser.add_argument('--events-file-path', default='source_mobile_app_configs.json', help='Path to the mobile app configs JSON file (default: source_mobile_app_configs.json)')
        mobile_app_configs_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate mobile app is found (default: ask)')
        mobile_app_configs_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

         # Synthetic configs migrator
        synthetic_configs_parser = subparsers.add_parser('synthetic-configs', help='Migrate synthetic monitoring configurations')
        synthetic_configs_parser.add_argument('--config-file', help='Path to configuration file')
        synthetic_configs_parser.add_argument('--source-token', help='API token for source backend')
        synthetic_configs_parser.add_argument('--source-url', help='URL for source backend')
        synthetic_configs_parser.add_argument('--target-token', help='API token for target backend')
        synthetic_configs_parser.add_argument('--target-url', help='URL for target backend')
        synthetic_configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        synthetic_configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for synthetic configs (api or file)')
        synthetic_configs_parser.add_argument('--events-file-path', default='source_synthetic_configs.json', help='Path to the synthetic configs JSON file (default: source_synthetic_configs.json)')
        synthetic_configs_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate synthetic config is found (default: ask)')
        synthetic_configs_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Synthetic smart alerts migrator
        synthetic_smart_alerts_parser = subparsers.add_parser('synthetic-smart-alerts', help='Migrate synthetic smart alert configurations')
        synthetic_smart_alerts_parser.add_argument('--config-file', help='Path to configuration file')
        synthetic_smart_alerts_parser.add_argument('--source-token', help='API token for source backend')
        synthetic_smart_alerts_parser.add_argument('--source-url', help='URL for source backend')
        synthetic_smart_alerts_parser.add_argument('--target-token', help='API token for target backend')
        synthetic_smart_alerts_parser.add_argument('--target-url', help='URL for target backend')
        synthetic_smart_alerts_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        synthetic_smart_alerts_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for synthetic smart alerts (api or file)')
        synthetic_smart_alerts_parser.add_argument('--events-file-path', default='source_synthetic_smart_alerts.json', help='Path to the synthetic smart alerts JSON file (default: source_synthetic_smart_alerts.json)')
        synthetic_smart_alerts_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate synthetic smart alert is found (default: ask)')
        synthetic_smart_alerts_parser.add_argument('--dry-run', action='store_true', help='Preview what would be migrated without making any changes')

        # Parse arguments
        args = parser.parse_args()
        
        # Check if a command was provided
        if not args.command:
            parser.print_help()
            sys.exit(1)
        
        # Convert args back to list for Config.from_args()
        arg_list = []
        for key, value in vars(args).items():
            if key != 'command' and value is not None:
                if isinstance(value, bool):
                    if value:
                        arg_list.append(f'--{key.replace("_", "-")}')
                else:
                    arg_list.append(f'--{key.replace("_", "-")}')
                    arg_list.append(str(value))
        
        # Parse configuration from command line arguments
        config = Config.from_args(arg_list)
        
        # Run the appropriate migrator
        if args.command == 'events':
            # Import and run the custom events migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'custom-events-specification'))
            from migrator import EventsMigrator
            migrator = EventsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'channels':
            # Import and run the alert channels migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'alert-channels'))
            from migrator import AlertChannelsMigrator
            migrator = AlertChannelsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'configs':
            # Import and run the alert configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'alert-configs'))
            from migrator import AlertConfigsMigrator
            migrator = AlertConfigsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'applications':
            # Import and run the application configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'application-configuration'))
            from migrator import ApplicationConfigMigrator
            migrator = ApplicationConfigMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'services':
            # Import and run the service configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'service-configuration'))
            from migrator import ServiceConfigMigrator
            migrator = ServiceConfigMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'endpoints':
            # Import and run the endpoint configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'endpoint-configuration'))
            from migrator import EndpointConfigMigrator
            migrator = EndpointConfigMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'custom-dashboards':
            # Import and run the custom dashboards migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'custom-dashboards'))
            from migrator import CustomDashboardsMigrator
            migrator = CustomDashboardsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'maintenance-configs':
            # Import and run the maintenance configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'maintenance-configs'))
            from migrator import MaintenanceConfigsMigrator
            migrator = MaintenanceConfigsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'application-smart-alerts':
            sys.path.append(os.path.join(os.path.dirname(__file__), 'application-smart-alerts'))
            from migrator import ApplicationSmartAlertsMigrator
            migrator = ApplicationSmartAlertsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'website-smart-alerts':
            sys.path.append(os.path.join(os.path.dirname(__file__), 'website-smart-alerts'))
            from migrator import WebsiteSmartAlertsMigrator
            migrator = WebsiteSmartAlertsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'mobile-app-smart-alerts':
            sys.path.append(os.path.join(os.path.dirname(__file__), 'mobile-app-smart-alerts'))
            from migrator import MobileAppSmartAlertsMigrator
            migrator = MobileAppSmartAlertsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'infrastructure-smart-alerts':
            sys.path.append(os.path.join(os.path.dirname(__file__), 'infrastructure-smart-alerts'))
            from migrator import InfrastructureSmartAlertsMigrator
            migrator = InfrastructureSmartAlertsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'website-configs':
            # Import and run the website configs migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'website-configs'))
            from migrator import WebsiteConfigMigrator
            migrator = WebsiteConfigMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'synthetic-configs':
            # Import and run the synthetic configs migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'synthetic-configs'))
            from migrator import SyntheticConfigMigrator  # noqa: F811
            migrator = SyntheticConfigMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'synthetic-smart-alerts':
            sys.path.append(os.path.join(os.path.dirname(__file__), 'synthetic-smart-alerts'))
            from migrator import SyntheticSmartAlertsMigrator
            migrator = SyntheticSmartAlertsMigrator(config)
            result = migrator.migrate()
            sys.exit(1 if result["failed"] > 0 else 0)

        elif args.command == 'mobile-app-configs':
            # Import and run the mobile app configs migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'mobile-app-configs'))
            from migrator import MobileAppConfigMigrator
            migrator = MobileAppConfigMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one mobile app was migrated or updated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no mobile apps were migrated
                sys.exit(1)

    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
