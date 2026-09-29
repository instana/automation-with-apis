import sys
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from permissions import check_permissions, dry_run_connectivity_check, DryRunAbortedError
from utils import print_dry_run_preview

_REQUIRED_PERMISSIONS = ["canConfigureMobileAppMonitoring"]

class MobileAppConfigMigrator:
    """Handles migration of mobile app monitoring configurations between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_mobile_app_config = "/api/mobile-app-monitoring/config"

        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _get_source_mobile_app_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all mobile app configurations from source backend or file.
        
        Returns:
            List of mobile app configurations or None if failed
        """
        if self.config.events_source.lower() == "file":
            try:
                file_path = self.config.events_file_path
                print(f"Reading mobile app configurations from {file_path} file...")
                with open(file_path, 'r') as f:
                    mobile_apps = json.load(f)
                print(f"Successfully loaded {len(mobile_apps)} mobile app configs from file")
                return mobile_apps
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                print("Make sure the file exists and contains valid JSON")
                return None
        else:
            try:
                print("Fetching mobile app configurations from source API...")
                response = requests.get(
                    f"{self.config.source_url}{self.req_mobile_app_config}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                response.raise_for_status()
                mobile_apps = response.json()
                # Write the response to the configured file path as a local backup
                with open(self.config.events_file_path, 'w') as f:
                    json.dump(mobile_apps, f, indent=2)
                print(f"Successfully fetched {len(mobile_apps)} mobile app configs from API")
                return mobile_apps
            except requests.exceptions.RequestException as e:
                print(f"Error fetching mobile app configurations from source API: {e}")
                return None

    def _get_target_mobile_app_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all mobile app configurations from target backend.
        
        Returns:
            List of mobile app configurations or None if failed
        """
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_mobile_app_config}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching mobile app configurations from target API: {e}")
            return None

    def _build_mobile_app_mapping(self, source_mobile_apps: List[Dict], target_mobile_apps: List[Dict]) -> Dict[str, str]:
        """Build mapping of source mobile app ID to target mobile app ID based on name matching."""
        mapping = {}
        target_by_name = {mobile_app.get('name'): mobile_app.get('id') for mobile_app in target_mobile_apps}

        for source_mobile_apps in source_mobile_apps:
            source_name = source_mobile_apps.get('name')
            source_id = source_mobile_apps.get('id')

            if source_name and source_id and source_name in target_by_name:
                mapping[source_id] = target_by_name[source_name]

        return mapping

    def _prompt_for_duplicate_mobile_app(self, mobile_app_name: str) -> str:
        """Prompt user for action when a duplicate mobile app is found.

        Respects config.on_duplicate when set to 'skip', 'update', or 'cancel'
        so that non-interactive runs (e.g. CI) do not block on stdin.

        Args:
            mobile_app_name: Name of the duplicate mobile app

        Returns:
            User choice: 'skip', 'update', or 'cancel'
        """
        # Honour non-interactive config setting first
        if self.config.on_duplicate in ('skip', 'update', 'cancel'):
            return self.config.on_duplicate

        while True:
            print(f"\nMobile app '{mobile_app_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing mobile app")
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

    def _update_mobile_app_config(self, mobile_app_name: str, target_id: str, target_name: str) -> bool:
        """Rename / update a mobile app in the target backend.

        The mobile app monitoring config PUT endpoint accepts the same query-param
        style as POST: PUT /api/mobile-app-monitoring/config/{id}?name=…

        If the source and target names are identical there is nothing to update —
        the API returns 400 for a rename-to-same-name request, so we skip the call.

        Args:
            mobile_app_name: The desired name (from source)
            target_id: The existing target mobile app ID to update
            target_name: The current name in the target (used to detect no-op renames)

        Returns:
            True if successful (or already up-to-date), False otherwise
        """
        if mobile_app_name == target_name:
            print(f"Mobile app '{mobile_app_name}' already has the correct name in target, skipping update")
            return True
        try:
            response = requests.put(
                f"{self.config.target_url}{self.req_mobile_app_config}/{target_id}?name={mobile_app_name}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            print(f"Updated mobile app '{mobile_app_name}' (Target ID: {target_id})")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error updating mobile app '{mobile_app_name}' (Target ID: {target_id}): {e}")
            return False

    def _create_mobile_app_config(self, mobile_app_name: str) -> Optional[str]:
        """Create a mobile app in the target backend using the name from source.

        Returns:
            The new target mobile app ID on success, or None on failure.
        """
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_mobile_app_config}?name={mobile_app_name}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            created = response.json()
            target_id = created.get('id') if isinstance(created, dict) else None
            if target_id:
                print(f"Successfully created mobile app '{mobile_app_name}' (Target ID: {target_id})")
                return target_id
            print(f"Successfully created mobile app '{mobile_app_name}' (no ID in response)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error creating mobile app '{mobile_app_name}' in target backend: {e}")
            return None
            
    def migrate(self) -> Dict[str, Any]:
        """Perform the migration of the mobile app configurations.

        Returns:
            Dictionary with counts and mobile app ID mapping
        """
        # Validate configuration
        self.config.validate()

        if self.config.dry_run:
            return self._dry_run()

        if not check_permissions(self.config, _REQUIRED_PERMISSIONS):
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "mobile_app_mapping": {}}

        print("Starting migration of mobile app configurations...")

        # Get source mobile apps
        source_mobile_apps = self._get_source_mobile_app_config()

        if source_mobile_apps is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "mobile_app_mapping": {}}

        if not source_mobile_apps:
            print("No source mobile app configurations found.")
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "mobile_app_mapping": {}}

        # Get target mobile app
        target_mobile_apps = self._get_target_mobile_app_config()

        if target_mobile_apps is None:
            return {"source": len(source_mobile_apps), "migrated": 0, "updated": 0, "skipped": 0, "mobile_app_mapping": {}}
        
        # Build initial mapping of existing mobile apps
        mobile_app_mapping = self._build_mobile_app_mapping(source_mobile_apps, target_mobile_apps)

        migrated_count = 0
        skipped_count = 0
        updated_count = 0

        # Process each source mobile app
        for source_mobile_app in source_mobile_apps:
            source_id = source_mobile_app.get('id')
            source_name = source_mobile_app.get('name')

            if not source_name or not source_id:
                print(f"Skipping mobile app with missing name or id: {source_mobile_app}")
                continue

            # Check if mobile app already exists in target (by name match)
            if source_id in mobile_app_mapping:
                choice = self._prompt_for_duplicate_mobile_app(str(source_name))
                if choice == 'skip':
                    print(f"Mobile app '{source_name}' already exists in target backend, skipping")
                    skipped_count += 1
                    continue
                elif choice == 'update':
                    target_id = mobile_app_mapping[source_id]
                    if self._update_mobile_app_config(str(source_name), target_id, str(source_name)):
                        updated_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break

            # Create mobile app in target; ID is read directly from the POST response body.
            # No extra GET call needed per mobile app.
            new_target_id = self._create_mobile_app_config(source_name)
            if new_target_id is not None:
                mobile_app_mapping[source_id] = new_target_id
                migrated_count += 1

        print(f"Migration complete. Found {len(source_mobile_apps)} source mobile apps, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_count} existing mobile apps.")

        return {
            "source": len(source_mobile_apps),
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "mobile_app_mapping": mobile_app_mapping,
        }

    def _dry_run(self) -> Dict[str, Any]:
        """Preview what would happen during migration without making any changes."""
        try:
            source_mobile_apps, target_mobile_apps = dry_run_connectivity_check(
                self.config,
                fetch_source=self._get_source_mobile_app_config,
                fetch_target=self._get_target_mobile_app_config,
                entity_name="mobile app configs",
                required_permissions=_REQUIRED_PERMISSIONS,
            )
        except DryRunAbortedError:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "mobile_app_mapping": {}}

        mobile_app_mapping = self._build_mobile_app_mapping(source_mobile_apps, target_mobile_apps)

        would_create = 0
        would_update = 0
        skipped_invalid = 0
        create_lines: List[str] = []
        update_lines: List[str] = []
        skip_lines: List[str] = []

        for source_mobile_app in source_mobile_apps:
            source_id = source_mobile_app.get('id')
            source_name = source_mobile_app.get('name')

            if not source_name or not source_id:
                skip_lines.append("  ✗ Would skip    (mobile app with missing name or id)")
                skipped_invalid += 1
                continue

            if source_id in mobile_app_mapping:
                update_lines.append(f"  ~ Would update  '{source_name}' (exists in target by name match)")
                would_update += 1
            else:
                create_lines.append(f"  ✓ Would create  '{source_name}'")
                would_create += 1

        skipped_total = skipped_invalid
        print_dry_run_preview(
            create_lines, update_lines, skip_lines,
            source_count=len(source_mobile_apps),
            target_count=len(target_mobile_apps),
            would_create=would_create,
            would_update=would_update,
            skipped_total=skipped_total,
            skipped_detail=f"{skipped_invalid} invalid",
            entity_name="mobile app configs",
        )
        return {
            "source": len(source_mobile_apps),
            "migrated": would_create,
            "updated": would_update,
            "skipped": skipped_total,
            "mobile_app_mapping": {},
        }
