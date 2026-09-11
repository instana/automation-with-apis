import sys
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config

class WebsiteConfigMigrator:
    """Handles migration of website monitoring configurations between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_website_config = "/api/website-monitoring/config"

        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _get_source_website_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all website configurations from source backend or file.
        
        Returns:
            List of website configurations or None if failed
        """
        if self.config.events_source.lower() == "file":
            try:
                file_path = self.config.events_file_path
                print(f"Reading website configurations from {file_path} file...")
                with open(file_path, 'r') as f:
                    websites = json.load(f)
                print(f"Successfully loaded {len(websites)} website configs from file")
                return websites
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                print("Make sure the file exists and contains valid JSON")
                return None
        else:
            try:
                print("Fetching website configurations from source API...")
                response = requests.get(
                    f"{self.config.source_url}{self.req_website_config}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                response.raise_for_status()
                websites = response.json()
                # Write the response to the configured file path as a local backup
                with open(self.config.events_file_path, 'w') as f:
                    json.dump(websites, f, indent=2)
                print(f"Successfully fetched {len(websites)} website configs from API")
                return websites
            except requests.exceptions.RequestException as e:
                print(f"Error fetching website configurations from source API: {e}")
                return None

    def _get_target_website_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all website configurations from target backend.
        
        Returns:
            List of website configurations or None if failed
        """
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_website_config}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching website configurations from target API: {e}")
            return None

    def _build_website_mapping(self, source_websites: List[Dict], target_websites: List[Dict]) -> Dict[str, str]:
        """Build mapping of source website ID to target website ID based on name matching."""
        mapping = {}
        target_by_name = {website.get('name'): website.get('id') for website in target_websites}

        for source_website in source_websites:
            source_name = source_website.get('name')
            source_id = source_website.get('id')

            if source_name and source_id and source_name in target_by_name:
                mapping[source_id] = target_by_name[source_name]

        return mapping

    def _prompt_for_duplicate_website(self, website_name: str) -> str:
        """Prompt user for action when a duplicate website is found.

        Respects config.on_duplicate when set to 'skip', 'update', or 'cancel'
        so that non-interactive runs (e.g. CI) do not block on stdin.

        Args:
            website_name: Name of the duplicate website

        Returns:
            User choice: 'skip', 'update', or 'cancel'
        """
        # Honour non-interactive config setting first
        if self.config.on_duplicate in ('skip', 'update', 'cancel'):
            return self.config.on_duplicate

        while True:
            print(f"\nWebsite '{website_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing website")
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

    def _update_website_config(self, website_name: str, target_id: str) -> bool:
        """Rename / update a website in the target backend.

        The website monitoring config PUT endpoint accepts the same query-param
        style as POST: PUT /api/website-monitoring/config/{id}?name=…

        Args:
            website_name: The desired name (from source)
            target_id: The existing target website ID to update

        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.put(
                f"{self.config.target_url}{self.req_website_config}/{target_id}?name={website_name}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            print(f"Updated website '{website_name}' (Target ID: {target_id})")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error updating website '{website_name}' (Target ID: {target_id}): {e}")
            return False

    def _create_website_config(self, website_name: str) -> Optional[str]:
        """Create a website in the target backend using the name from source.

        Returns:
            The new target website ID on success, or None on failure.
        """
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_website_config}?name={website_name}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            created = response.json()
            target_id = created.get('id') if isinstance(created, dict) else None
            if target_id:
                print(f"Successfully created website '{website_name}' (Target ID: {target_id})")
                return target_id
            print(f"Successfully created website '{website_name}' (no ID in response)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error creating website '{website_name}' in target backend: {e}")
            return None
            
    def migrate(self) -> Dict[str, Any]:
        """Perform the migration of the website configurations.

        Returns:
            Dictionary with counts and website ID mapping
        """
        # Validate configuration
        self.config.validate()

        print("Starting migration of website configurations...")

        # Get source websites
        source_websites = self._get_source_website_config()

        if source_websites is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "website_mapping": {}}

        if not source_websites:
            print("No source website configurations found.")
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "website_mapping": {}}

        # Get target websites
        target_websites = self._get_target_website_config()

        if target_websites is None:
            return {"source": len(source_websites), "migrated": 0, "updated": 0, "skipped": 0, "website_mapping": {}}
        
        # Build initial mapping of existing websites
        website_mapping = self._build_website_mapping(source_websites, target_websites)

        migrated_count = 0
        skipped_count = 0
        updated_count = 0

        # Process each source website
        for source_website in source_websites:
            source_id = source_website.get('id')
            source_name = source_website.get('name')

            if not source_name or not source_id:
                print(f"Skipping website with missing name or id: {source_website}")
                continue

            # Check if website already exists in target (by name match)
            if source_id in website_mapping:
                choice = self._prompt_for_duplicate_website(str(source_name))
                if choice == 'skip':
                    print(f"Website '{source_name}' already exists in target backend, skipping")
                    skipped_count += 1
                    continue
                elif choice == 'update':
                    target_id = website_mapping[source_id]
                    if self._update_website_config(str(source_name), target_id):
                        updated_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break

            # Create website in target; ID is read directly from the POST response body.
            # No extra GET call needed per website.
            new_target_id = self._create_website_config(source_name)
            if new_target_id is not None:
                website_mapping[source_id] = new_target_id
                migrated_count += 1

        print(f"Migration complete. Found {len(source_websites)} source websites, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_count} existing websites.")

        return {
            "source": len(source_websites),
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "website_mapping": website_mapping,
        }
