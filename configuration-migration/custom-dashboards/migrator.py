
"""Core functionality for migrating custom dashboards between backends.

This module now uses the async implementation for better performance.
The synchronous interface is maintained for backward compatibility.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config

# Import the async implementation
try:
    from migrator_async import CustomDashboardsMigratorAsync
    ASYNC_AVAILABLE = True
except ImportError as e:
    ASYNC_AVAILABLE = False
    print(f"Warning: Async dependencies not available. Install aiohttp and aiohttp-retry for better performance.")
    print(f"Import error details: {e}")

# Keep the old synchronous implementation as fallback
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional


class CustomDashboardsMigrator:
    """Handles migration of custom dashboards between backends.
    
    This class now delegates to the async implementation when available,
    maintaining backward compatibility with the synchronous interface.
    """

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.
        
        Args:
            config: Configuration object with backend details
        """
        self.config = config
        
        # Use async implementation if available
        if ASYNC_AVAILABLE:
            self._async_migrator = CustomDashboardsMigratorAsync(config)
            self._use_async = True
        else:
            self._use_async = False
            self.req_custom_dashboards = "/api/custom-dashboard"
            self.req_shareable_users = "/api/settings/users"
            
            # Disable SSL warnings if verify_ssl is False
            if not config.verify_ssl:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def migrate(self) -> Dict[str, int]:
        """Perform the migration of custom dashboards.
        
        Returns:
            Dictionary with counts of source, migrated, updated, and skipped dashboards
        """
        # Use async implementation if available for better performance
        if self._use_async:
            return self._async_migrator.migrate()
        
        # Fallback to synchronous implementation
        return self._migrate_sync()
    
    def _migrate_sync(self) -> Dict[str, int]:
        """Synchronous migration implementation (fallback).
        
        Returns:
            Dictionary with counts of source, migrated, updated, and skipped dashboards
        """
        # Validate configuration before proceeding
        self.config.validate()
        
        print("Starting migration of custom dashboards (synchronous mode)...")
        print("Note: Install aiohttp and aiohttp-retry for 10x faster performance!")
        
        # Get source dashboards
        source_dashboards = self._get_source_dashboards()
        if source_dashboards is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}
        
        # Get target dashboards to avoid duplicates
        target_dashboards = self._get_target_dashboards()
        if target_dashboards is None:
            return {"source": len(source_dashboards), "migrated": 0, "updated": 0, "skipped": 0}
            
        # Get users from source and target for mapping
        source_users = self._get_shareable_users(self.config.source_url, self.config.get_source_headers())
        target_users = self._get_shareable_users(self.config.target_url, self.config.get_target_headers())

        if source_users is None:
            print("Could not retrieve source users, aborting migration.")
            return {"source": 0, "migrated": 0, "skipped": 0, "updated": 0}
        
        if target_users is None:
            print("Could not retrieve target users, aborting migration.")
            return {"source": len(source_dashboards), "migrated": 0, "skipped": 0, "updated": 0}

        user_map: Dict[str, str] = {}
        if not target_users:
            print("No users found in the target system. All dashboards will be assigned to the default owner ID.")
            # user_map remains empty, so all dashboards will fall back to default_owner_id
        else:
            user_map = self._map_users(source_users, target_users)

        target_dashboard_titles = [d.get('title') for d in target_dashboards if d.get('title')]
        
        migrated_count = 0
        skipped_count = 0
        updated_count = 0
        source_dashboards_count = len(source_dashboards)
        
        for dashboard in source_dashboards:
            dashboard_title = dashboard.get('title')

            if not dashboard_title:
                print("Skipping dashboard with no title")
                skipped_count += 1
                continue

            # Remove the 'owner' field if it exists
            if 'owner' in dashboard:
                del dashboard['owner']
            
            # Remove ownerId - not needed in POST payload
            if 'ownerId' in dashboard:
                del dashboard['ownerId']

            # Set accessRules to GLOBAL READ_WRITE with empty relatedId
            # This is the working structure that persists dashboards correctly
            dashboard['accessRules'] = [{
                'accessType': 'READ_WRITE',
                'relationType': 'GLOBAL',
                'relatedId': ''
            }]
            
            # IMPORTANT: Keep the 'id' field from source dashboard
            # The API requires this field to properly create the dashboard
            
            # Ensure widgets are present
            if 'widgets' not in dashboard or not dashboard['widgets']:
                print(f"Warning: Dashboard '{dashboard_title}' has no widgets. Skipping.")
                skipped_count += 1
                continue
            
            # Validate widget structure - each widget must have required fields
            widget_validation_failed = False
            for idx, widget in enumerate(dashboard['widgets']):
                missing_fields = []
                if 'id' not in widget or not widget['id']:
                    missing_fields.append('id')
                if 'width' not in widget or widget['width'] < 1:
                    missing_fields.append('width')
                if 'height' not in widget or widget['height'] < 1:
                    missing_fields.append('height')
                if 'config' not in widget:
                    missing_fields.append('config')
                
                if missing_fields:
                    print(f"Error: Widget {idx} in dashboard '{dashboard_title}' is missing required fields: {', '.join(missing_fields)}")
                    print(f"Widget data: {widget}")
                    widget_validation_failed = True
                    break
            
            if widget_validation_failed:
                skipped_count += 1
                continue

            if dashboard_title in target_dashboard_titles:
                # Check on_duplicate setting
                if self.config.on_duplicate == "update":
                    print(f"⟳ Dashboard '{dashboard_title}' already exists, updating...")
                    if self._update_dashboard(dashboard, dashboard_title, target_dashboards):
                        updated_count += 1
                    else:
                        skipped_count += 1
                    continue
                elif self.config.on_duplicate == "skip":
                    print(f"⊘ Dashboard '{dashboard_title}' already exists, skipping...")
                    skipped_count += 1
                    continue
                else:
                    # on_duplicate == "ask" - prompt user
                    choice = self._prompt_for_duplicate_dashboard(dashboard_title)
                    if choice == 'skip':
                        print(f"Skipping dashboard '{dashboard_title}' - already exists in target system")
                        skipped_count += 1
                        continue
                    elif choice == 'update':
                        print(f"Updating dashboard '{dashboard_title}' - already exists in target system")
                        if self._update_dashboard(dashboard, dashboard_title, target_dashboards):
                            updated_count += 1
                        else:
                            skipped_count += 1
                        continue
                    elif choice == 'cancel':
                        print("Migration cancelled by user")
                        break
            
            # IMPORTANT: Keep the 'id' field from source dashboard
            # The API requires this field to properly create the dashboard
            # Do NOT delete it!

            if self._create_dashboard(dashboard):
                migrated_count += 1
            else:
                skipped_count += 1
        
        print(f"Migration complete. Found {source_dashboards_count} source dashboards, "
              f"migrated {migrated_count} custom dashboards, updated {updated_count} dashboards, "
              f"skipped {skipped_count} dashboards.")
        
        return {
            "source": source_dashboards_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count
        }

    def _map_users(self, source_users: List[Dict[str, Any]], target_users: List[Dict[str, Any]]) -> Dict[str, str]:
        """Map users between source and target backends based on email.
        
        Args:
            source_users: List of users from the source backend
            target_users: List of users from the target backend
            
        Returns:
            A dictionary mapping source user IDs to target user IDs
        """
        user_map: Dict[str, str] = {}
        if not source_users or not target_users:
            return user_map

        target_user_emails = {user['email']: user['id'] for user in target_users if 'email' in user and 'id' in user}
        
        for source_user in source_users:
            if 'email' in source_user and 'id' in source_user:
                source_email = source_user.get('email')
                if source_email in target_user_emails:
                    user_map[source_user['id']] = target_user_emails[source_email]
        
        return user_map
    
    def _prompt_for_duplicate_dashboard(self, dashboard_title: str) -> str:
        """Prompt user for action when a duplicate dashboard is found.
        
        Args:
            dashboard_title: Name of the duplicate dashboard
            
        Returns:
            User choice: 'skip', 'update', or 'cancel'
        """
        if self.config.on_duplicate != "ask":
            print(f"Non-interactive mode: Using '{self.config.on_duplicate}' for duplicate dashboard '{dashboard_title}'.")
            return self.config.on_duplicate

        if not sys.stdin.isatty():
            print(f"Non-interactive mode: Skipping duplicate dashboard '{dashboard_title}'.")
            return 'skip'

        while True:
            print(f"\nDashboard '{dashboard_title}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing dashboard")
            print("  [c] Cancel migration")
            
            choice = input("Enter your choice [s/u/c]: ").lower()
            
            if choice in ['s', 'skip']:
                return 'skip'
            elif choice in ['u', 'update']:
                return 'update'
            elif choice in ['c', 'cancel']:
                return 'cancel'
            else:
                print("Invalid choice. Please try again.")

    def _get_source_dashboards(self) -> Optional[List[Dict[str, Any]]]:
        """Get all custom dashboards from source backend or file.
        
        Returns:
            List of custom dashboards or None if failed
        """
        try:
            print("Fetching custom dashboard IDs from API endpoint...")
            response = requests.get(
                f"{self.config.source_url}{self.req_custom_dashboards}",
                headers=self.config.get_source_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            dashboard_ids = [d['id'] for d in response.json()]
            
            full_dashboards = []
            print(f"Fetching details for {len(dashboard_ids)} dashboards...")
            for dashboard_id in dashboard_ids:
                detail_response = requests.get(
                    f"{self.config.source_url}{self.req_custom_dashboards}/{dashboard_id}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                detail_response.raise_for_status()
                dashboard_data = detail_response.json()
                full_dashboards.append(dashboard_data)
            
            print(f"Successfully fetched {len(full_dashboards)} dashboards with full details from API")
            return full_dashboards
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving source dashboards from API: {e}")
            return None

    def _get_target_dashboards(self) -> Optional[List[Dict[str, Any]]]:
        """Get all custom dashboards from target backend.
        
        Returns:
            List of custom dashboards or None if failed
        """
        try:
            print("Fetching custom dashboard IDs from target API endpoint...")
            response = requests.get(
                f"{self.config.target_url}{self.req_custom_dashboards}", 
                headers=self.config.get_target_headers(), 
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            dashboard_ids = [d['id'] for d in response.json()]

            full_dashboards = []
            print(f"Fetching details for {len(dashboard_ids)} target dashboards...")
            for dashboard_id in dashboard_ids:
                detail_response = requests.get(
                    f"{self.config.target_url}{self.req_custom_dashboards}/{dashboard_id}",
                    headers=self.config.get_target_headers(),
                    verify=self.config.verify_ssl
                )
                detail_response.raise_for_status()
                full_dashboards.append(detail_response.json())

            print(f"Successfully fetched {len(full_dashboards)} target dashboards with full details from API")
            return full_dashboards
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving target dashboards: {e}")
            return None

    def _get_shareable_users(self, base_url: str, headers: Dict[str, str]) -> Optional[List[Dict[str, Any]]]:
        """Get all shareable users from a backend.
        
        Args:
            base_url: Base URL of the backend
            headers: Headers for authentication
            
        Returns:
            List of shareable users or None if failed
        """
        try:
            response = requests.get(
                f"{base_url}{self.req_shareable_users}",
                headers=headers,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving shareable users: {e}")
            return None

    def _create_dashboard(self, dashboard: Dict[str, Any]) -> bool:
        """Create a custom dashboard in the target backend.
        
        Args:
            dashboard: Dashboard configuration to create
            
        Returns:
            True if successful, False otherwise
        """
        dashboard_title = dashboard.get('title', 'N/A')
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_custom_dashboards}",
                headers=self.config.get_target_headers(),
                json=dashboard,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            new_dashboard = response.json()
            
            if 'id' in new_dashboard:
                print(f"Migrated custom dashboard '{dashboard_title}' (Target ID: {new_dashboard['id']})")
                return True
            else:
                print(f"Failed to migrate custom dashboard '{dashboard_title}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to migrate custom dashboard '{dashboard_title}'")
            print(f"Error: {e}")
            if e.response is not None:
                try:
                    print(f"API Error Details: {e.response.json()}")
                except json.JSONDecodeError:
                    print(f"API Error Details (raw): {e.response.text}")
            print(f"JSON payload sent: {json.dumps(dashboard, indent=2)}")
            return False
            
    def _update_dashboard(self, dashboard: Dict[str, Any], dashboard_title: str, target_dashboards: List[Dict[str, Any]]) -> bool:
        """Update an existing custom dashboard in the target backend.
        
        Args:
            dashboard: Dashboard configuration to update
            dashboard_title: Name of the dashboard for logging
            target_dashboards: List of dashboards from the target system
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not target_dashboards:
                print(f"No target dashboards provided for updating '{dashboard_title}'")
                return False
            
            target_dashboard = next((d for d in target_dashboards if d.get('title') == dashboard_title), None)
            if not target_dashboard or 'id' not in target_dashboard:
                print(f"Failed to find matching target dashboard for '{dashboard_title}'")
                return False
            
            target_dashboard_id = target_dashboard['id']
            print(f"Updating dashboard with ID: {target_dashboard_id}")
            
            if 'id' in dashboard:
                del dashboard['id']
            
            response = requests.put(
                f"{self.config.target_url}{self.req_custom_dashboards}/{target_dashboard_id}",
                headers=self.config.get_target_headers(),
                json=dashboard,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            updated_dashboard = response.json()
            
            if 'id' in updated_dashboard:
                print(f"Updated custom dashboard '{dashboard_title}' (Target ID: {updated_dashboard['id']})")
                return True
            else:
                print(f"Failed to update custom dashboard '{dashboard_title}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to update custom dashboard '{dashboard_title}'")
            print(f"Error: {e}")
            if e.response is not None:
                try:
                    print(f"API Error Details: {e.response.json()}")
                except json.JSONDecodeError:
                    print(f"API Error Details (raw): {e.response.text}")
            return False
