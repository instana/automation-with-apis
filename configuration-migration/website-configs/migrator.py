import sys
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config

class WebsiteConfigMigrator:
    "Handles migration of website configs"

    def __init__(self, config: Config):
        """Initializes the migrator with the given config
        Args:
            config:  Configuration object with backend details
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
        if self.config.events_source=="file":
            try:
                with open(self.config.events_file_path, 'r') as f:
                    return json.load(f)
            except FileNotFoundError:
                print(f"ERROR: Source file {self.config.events_file_path} not found")
                return []
            except json.JSONDecodeError:
                print(f"ERROR: Invalid JSON in source file {self.config.events_file_path}")
                return []
        else:
            try:
                response = requests.get(f"{self.config.source_url}{self.req_website_config}",
                headers=self.config.get_source_headers(),
                verify=self.config.verify_ssl,
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"Error fetching website configurations from source API: {e}")
                return []

    def _get_target_website_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all website configurations from target backend or file.
        
        Returns:
            List of website configurations or None if failed
        """
        try:
            response = requests.get(f"{self.config.target_url}{self.req_website_config}",
            headers = self.config.get_target_headers(),
            verify = self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json() 
        except Exception as e:
            print(f"Error fetching website configurations from target API: {e}")
            return []

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

    def _create_website_config(self, website_name: str) -> bool:
        """Create a website in the target backend using the name from source."""

        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_website_config}?name={website_name}",
                headers=self.config.get_target_headers(),
                json=[],
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            print(f"Successfully created website '{website_name}'")
            return True
        except Exception as e:
            print(f"Error creating website '{website_name}' in target backend: {e}")
            return False
            
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

        if not source_websites:
            return {"source": 0, "migrated": 0, "skipped": 0, "website_mapping": {}}
        
        # Get target websites
        target_websites = self._get_target_website_config()

        if target_websites is None:
            return {"source": len(source_websites), "migrated": 0, "skipped": 0, "website_mapping": {}}
        
        # Build initial mapping of existing websites
        website_mapping = self._build_website_mapping(source_websites, target_websites)

        migrated_count = 0
        skipped_count = 0

        # Process each source website
        for source_website in source_websites:
            source_id = source_website.get('id')
            source_name = source_website.get('name')

            if not source_name or not source_id:
                print(f"Skipping website with missing name or id: {source_website}")
                continue

            # Check if website already exists in target
            if source_id in website_mapping:
                print(f"Website '{source_name}' already exists in target backend, skipping")
                skipped_count += 1
                continue

            # Create website in target
            if self._create_website_config(source_name):
                # Get updated target websites to find the newly created website's ID
                updated_target_websites = self._get_target_website_config()
                if updated_target_websites:
                    for target_website in updated_target_websites:
                        if target_website.get('name') == source_name:
                            website_mapping[source_id] = target_website.get('id')
                            break
                migrated_count += 1

        print(f"Migration complete. Found {len(source_websites)} source websites, "
              f"migrated {migrated_count} websites, skipped {skipped_count} existing websites.")
        
        return {
            "source": len(source_websites),
            "migrated": migrated_count,
            "skipped": skipped_count,
            "website_mapping": website_mapping
        }
