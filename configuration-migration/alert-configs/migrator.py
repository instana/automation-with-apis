import json
import requests
import urllib3
from typing import Dict, List, Any
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config


class AlertConfigsMigrator:
    def __init__(self, config: Config):
        self.config = config
        self.req_alert_configs = "/api/events/settings/alerts"
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        self.config.validate()
        source_configs = self._get_source_configs()
        target_configs = self._get_target_configs()
        
        migrated_count = 0
        updated_count = 0
        skipped_count = 0
        
        print(f"Starting migration of alert configurations...")
        
        if self.config.events_source == "file":
            print(f"Reading alert configurations from {self.config.events_file_path} file...")
        else:
            print(f"Reading alert configurations from source API...")
        
        print(f"Successfully loaded {len(source_configs)} alert configurations from {'file' if self.config.events_source == 'file' else 'API'}")
        print()
        
        target_config_names = {config.get('alertName') for config in target_configs if config.get('alertName')}
        
        for config in source_configs:
            config_name = config.get('alertName')
            if not config_name:
                continue
                
            if config_name in target_config_names:
                choice = self._prompt_for_duplicate_config(str(config_name))
                if choice == 'skip':
                    print(f"Skipping alert configuration '{config_name}' - already exists in target system")
                    skipped_count += 1
                    continue
                elif choice == 'update':
                    print(f"Updating alert configuration '{config_name}' - already exists in target system")
                    target_config = next((c for c in target_configs if c.get('alertName') == config_name), None)
                    if target_config and self._update_config(config, target_config.get('id'), str(config_name)):
                        updated_count += 1
                    continue
                elif choice == 'cancel':
                    break
                    
            if self._create_config(config, str(config_name)):
                migrated_count += 1
        
        print(f"Migration complete. Found {len(source_configs)} source alert configurations, migrated {migrated_count} alert configurations, updated {updated_count} alert configurations, skipped {skipped_count} existing alert configurations.")
        
        return {
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count
        }

    def _get_source_configs(self) -> List[Dict[str, Any]]:
        if self.config.events_source == "file":
            try:
                with open(self.config.events_file_path, 'r') as f:
                    return json.load(f)
            except FileNotFoundError:
                print(f"Error: Source file '{self.config.events_file_path}' not found.")
                return []
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON in source file '{self.config.events_file_path}'.")
                return []
        else:
            try:
                response = requests.get(
                    f"{self.config.source_url}{self.req_alert_configs}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"Error fetching alert configurations from source API: {e}")
                return []

    def _get_target_configs(self) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_alert_configs}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching alert configurations from target API: {e}")
            return []

    def _prompt_for_duplicate_config(self, config_name: str) -> str:
        while True:
            print(f"Alert configuration '{config_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing alert configuration")
            print("  [c] Cancel migration")
            choice = input("Enter your choice [s/u/c]: ").lower().strip()
            
            if choice in ['s', 'skip']:
                return 'skip'
            elif choice in ['u', 'update']:
                return 'update'
            elif choice in ['c', 'cancel']:
                return 'cancel'
            else:
                print("Invalid choice. Please enter 's', 'u', or 'c'.")

    def _create_config(self, config: Dict[str, Any], config_name: str) -> bool:
        try:
            formatted_config = self._format_config_for_api(config)
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_configs}/{formatted_config['id']}",
                json=formatted_config,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            result = response.json()
            print(f"Created alert configuration '{config_name}' (Target ID: {result.get('id', 'unknown')})")
            return True
        except Exception as e:
            print(f"Error creating alert configuration '{config_name}': {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> bool:
        try:
            formatted_config = self._format_config_for_api(config)
            print(f"Updating alert configuration with ID: {target_id}")
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_configs}/{target_id}",
                json=formatted_config,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            result = response.json()
            print(f"Updated alert configuration '{config_name}' (Target ID: {result.get('id', 'unknown')})")
            return True
        except Exception as e:
            print(f"Error updating alert configuration '{config_name}': {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any]) -> Dict[str, Any]:
        formatted = config.copy()
        
        # Remove read-only fields that shouldn't be sent in API requests
        read_only_fields = ['lastUpdated', 'invalid', 'alertChannelNames', 'applicationNames']
        for field in read_only_fields:
            if field in formatted:
                del formatted[field]
        
        # Ensure required fields are present
        if 'id' not in formatted:
            raise ValueError("Alert configuration must have an 'id' field")
        
        if 'alertName' not in formatted:
            raise ValueError("Alert configuration must have an 'alertName' field")
        
        # Ensure eventFilteringConfiguration is properly structured
        if 'eventFilteringConfiguration' not in formatted:
            formatted['eventFilteringConfiguration'] = {
                "query": None,
                "ruleIds": [],
                "eventTypes": [],
                "applicationAlertConfigIds": [],
                "validVersion": 1
            }
        
        # Ensure customPayloadFields is an array
        if 'customPayloadFields' not in formatted:
            formatted['customPayloadFields'] = []
        
        # Ensure integrationIds is an array
        if 'integrationIds' not in formatted:
            formatted['integrationIds'] = []
        
        # Ensure muteUntil has a default value
        if 'muteUntil' not in formatted:
            formatted['muteUntil'] = 0
        
        # Ensure includeEntityNameInLegacyAlerts has a default value
        if 'includeEntityNameInLegacyAlerts' not in formatted:
            formatted['includeEntityNameInLegacyAlerts'] = False
        
        return formatted
