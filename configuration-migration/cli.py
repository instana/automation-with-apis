"""Command-line interface for Custom Events, Alert Channels, Alert Configurations, Custom Dashboards, and Website Configs Migrator."""

import sys
import argparse
from config import Config
import sys
import os

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
        events_parser.add_argument('--events-file-path', help='Path to the source events JSON file (when using file source)')
        
        # Alert channels migrator
        channels_parser = subparsers.add_parser('channels', help='Migrate alert channels')
        channels_parser.add_argument('--config-file', help='Path to configuration file')
        channels_parser.add_argument('--source-token', help='API token for source backend')
        channels_parser.add_argument('--source-url', help='URL for source backend')
        channels_parser.add_argument('--target-token', help='API token for target backend')
        channels_parser.add_argument('--target-url', help='URL for target backend')
        channels_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        channels_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for alert channels (api or file)')
        channels_parser.add_argument('--events-file-path', help='Path to the source channels JSON file (when using file source)')
        
        # Alert configurations migrator
        configs_parser = subparsers.add_parser('configs', help='Migrate alert configurations')
        configs_parser.add_argument('--config-file', help='Path to configuration file')
        configs_parser.add_argument('--source-token', help='API token for source backend')
        configs_parser.add_argument('--source-url', help='URL for source backend')
        configs_parser.add_argument('--target-token', help='API token for target backend')
        configs_parser.add_argument('--target-url', help='URL for target backend')
        configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for alert configurations (api or file)')
        configs_parser.add_argument('--events-file-path', help='Path to the source configurations JSON file (when using file source)')

        # Application configurations migrator
        applications_parser = subparsers.add_parser('applications', help='Migrate application configurations (Application Perspectives)')
        applications_parser.add_argument('--config-file', help='Path to configuration file')
        applications_parser.add_argument('--source-token', help='API token for source backend')
        applications_parser.add_argument('--source-url', help='URL for source backend')
        applications_parser.add_argument('--target-token', help='API token for target backend')
        applications_parser.add_argument('--target-url', help='URL for target backend')
        applications_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        applications_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate application config is found (default: ask)')

        # Service configurations migrator
        services_parser = subparsers.add_parser('services', help='Migrate service configurations')
        services_parser.add_argument('--config-file', help='Path to configuration file')
        services_parser.add_argument('--source-token', help='API token for source backend')
        services_parser.add_argument('--source-url', help='URL for source backend')
        services_parser.add_argument('--target-token', help='API token for target backend')
        services_parser.add_argument('--target-url', help='URL for target backend')
        services_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        services_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate service config is found (default: ask)')

        # Endpoint configurations migrator
        endpoints_parser = subparsers.add_parser('endpoints', help='Migrate endpoint configurations')
        endpoints_parser.add_argument('--config-file', help='Path to configuration file')
        endpoints_parser.add_argument('--source-token', help='API token for source backend')
        endpoints_parser.add_argument('--source-url', help='URL for source backend')
        endpoints_parser.add_argument('--target-token', help='API token for target backend')
        endpoints_parser.add_argument('--target-url', help='URL for target backend')
        endpoints_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        endpoints_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate endpoint config is found (default: ask)')

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

        # Maintenance configurations migrator
        maintenance_parser = subparsers.add_parser('maintenance-configs', help='Migrate maintenance configurations')
        maintenance_parser.add_argument('--config-file', help='Path to configuration file')
        maintenance_parser.add_argument('--source-token', help='API token for source backend')
        maintenance_parser.add_argument('--source-url', help='URL for source backend')
        maintenance_parser.add_argument('--target-token', help='API token for target backend')
        maintenance_parser.add_argument('--target-url', help='URL for target backend')
        maintenance_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        maintenance_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for maintenance configurations (api or file)')
        maintenance_parser.add_argument('--events-file-path', help='Path to the maintenance configurations JSON file (when using file source)')
        maintenance_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a maintenance configuration already exists in the target (default: ask)')
        maintenance_parser.add_argument('--request-timeout', type=int, help='Timeout per request in seconds (default: 30)')

        # Website configs migrator
        website_configs_parser = subparsers.add_parser('website-configs', help='Migrate website monitoring configurations')
        website_configs_parser.add_argument('--config-file', help='Path to configuration file')
        website_configs_parser.add_argument('--source-token', help='API token for source backend')
        website_configs_parser.add_argument('--source-url', help='URL for source backend')
        website_configs_parser.add_argument('--target-token', help='API token for target backend')
        website_configs_parser.add_argument('--target-url', help='URL for target backend')
        website_configs_parser.add_argument('--no-verify-ssl', action='store_true', help='Disable SSL certificate verification')
        website_configs_parser.add_argument('--events-source', choices=['api', 'file'], help='Source for website configs (api or file)')
        website_configs_parser.add_argument('--events-file-path', help='Path to the website configs JSON file (when using file source)')
        website_configs_parser.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'], help='Action to take when a duplicate website is found (default: ask)')

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
            
            # Exit with success if at least one event was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no events were migrated
                sys.exit(1)
                
        elif args.command == 'channels':
            # Import and run the alert channels migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'alert-channels'))
            from migrator import AlertChannelsMigrator
            migrator = AlertChannelsMigrator(config)
            result = migrator.migrate()

            # Exit with error only when one or more channels failed
            sys.exit(1 if result["failed"] > 0 else 0)
                
        elif args.command == 'configs':
            # Import and run the alert configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'alert-configs'))
            from migrator import AlertConfigsMigrator
            migrator = AlertConfigsMigrator(config)
            result = migrator.migrate()
            
            # Exit with success if at least one configuration was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no configurations were migrated
                sys.exit(1)

        elif args.command == 'applications':
            # Import and run the application configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'application-configuration'))
            from migrator import ApplicationConfigMigrator
            migrator = ApplicationConfigMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one application config was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                sys.exit(1)

        elif args.command == 'services':
            # Import and run the service configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'service-configuration'))
            from migrator import ServiceConfigMigrator
            migrator = ServiceConfigMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one service config was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                sys.exit(1)

        elif args.command == 'endpoints':
            # Import and run the endpoint configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'endpoint-configuration'))
            from migrator import EndpointConfigMigrator
            migrator = EndpointConfigMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one endpoint config was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                sys.exit(1)

        elif args.command == 'custom-dashboards':
            # Import and run the custom dashboards migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'custom-dashboards'))
            from migrator import CustomDashboardsMigrator
            migrator = CustomDashboardsMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one dashboard was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no dashboards were migrated
                sys.exit(1)

        elif args.command == 'maintenance-configs':
            # Import and run the maintenance configurations migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'maintenance-configs'))
            from migrator import MaintenanceConfigsMigrator
            migrator = MaintenanceConfigsMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one configuration was migrated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no configurations were migrated
                sys.exit(1)

        elif args.command == 'website-configs':
            # Import and run the website configs migrator
            sys.path.append(os.path.join(os.path.dirname(__file__), 'website-configs'))
            from migrator import WebsiteConfigMigrator
            migrator = WebsiteConfigMigrator(config)
            result = migrator.migrate()

            # Exit with success if at least one website was migrated or updated
            if result["migrated"] > 0 or result["updated"] > 0:
                sys.exit(0)
            else:
                # Exit with error code if no websites were migrated
                sys.exit(1)

    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

# Made with Bob
