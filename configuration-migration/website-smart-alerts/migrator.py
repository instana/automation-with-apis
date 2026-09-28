import copy
import json
import requests
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator

from instana_client.api.event_settings_api import EventSettingsApi
from instana_client.models.website_alert_config import WebsiteAlertConfig
from instana_client.exceptions import ApiException

_API_ENDPOINT = "/api/events/settings/website-alert-configs"


class WebsiteSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "website smart alert"
    api_class = EventSettingsApi

    def __init__(self, config: Config):
        super().__init__(config)
        self.website_id_map: Dict[str, str] = {}
        self.website_name_map: Dict[str, str] = {}
        self._website_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.website_id_map = self._get_website_id_map()

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{self.config.source_url}{_API_ENDPOINT}",
                headers=self.config.get_source_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            configs = response.json()

            with open(self.config.events_file_path, 'w') as f:
                json.dump(configs, f, indent=2)

            return configs
        except requests.RequestException as e:
            print(f"Error retrieving source alert configurations from API: {e}")
            return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{self.config.target_url}{_API_ENDPOINT}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            response = requests.post(
                f"{self.config.target_url}{_API_ENDPOINT}",
                json=payload,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            result_id = response.json().get('id', 'unknown')
            print(f"Migrated website smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping website smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to migrate website smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            response = requests.put(
                f"{self.config.target_url}{_API_ENDPOINT}/{target_id}",
                json=payload,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            result_id = response.json().get('id', target_id)
            print(f"Updated website smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping website smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to update website smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        self._strip_common_metadata(formatted)

        if isinstance(formatted.get('threshold'), dict):
            formatted['threshold'].pop('lastUpdated', None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap websiteId to the corresponding target website ID.
        src_website_id: Optional[str] = formatted.get('websiteId')
        if src_website_id:
            if src_website_id in self.website_id_map:
                formatted['websiteId'] = self.website_id_map[src_website_id]
            elif self._website_map_fetched and validate:
                src_website_name = self.website_name_map.get(src_website_id, src_website_id)
                raise ValueError(
                    f"website '{src_website_name}' not found in target — "
                    "ensure the website exists in the target system before migrating smart alerts"
                )

        return formatted

    def _get_website_id_map(self) -> Dict[str, str]:
        website_id_map: Dict[str, str] = {}
        try:
            source_websites: List[Dict[str, Any]] = []
            website_endpoint = '/api/website-monitoring/config'

            if self.config.source_url and self.config.source_token:
                response = requests.get(
                    f"{self.config.source_url}{website_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_websites = response.json()

            response = requests.get(
                f"{self.config.target_url}{website_endpoint}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_websites = response.json() if response.status_code == 200 else []

            target_by_name: Dict[str, str] = {
                str(w['name']): str(w['id'])
                for w in target_websites
                if w.get('name') and w.get('id')
            }
            for sw in source_websites:
                sw_name = sw.get('name')
                sw_id = sw.get('id')
                if sw_id and sw_name:
                    self.website_name_map[str(sw_id)] = str(sw_name)
                if sw_name and sw_id and sw_name in target_by_name:
                    website_id_map[str(sw_id)] = target_by_name[str(sw_name)]

            self._website_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build website ID map: {e}")

        return website_id_map
