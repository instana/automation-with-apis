import copy
import requests
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator
from utils import build_api

from instana_client.api.event_settings_api import EventSettingsApi
from instana_client.models.website_alert_config import WebsiteAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> EventSettingsApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, EventSettingsApi)


class WebsiteSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "website smart alert"
    api_class = EventSettingsApi
    model_class = WebsiteAlertConfig

    def __init__(self, config: Config):
        super().__init__(config)
        self.website_id_map: Dict[str, str] = {}
        self._website_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.website_id_map = self._get_website_id_map()

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.source_url, self.config.source_token)
            results = api.find_active_website_alert_configs(website_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving source alert configurations from API: {e}")
            return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            results = api.find_active_website_alert_configs(website_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = WebsiteAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.create_website_alert_config(sdk_config)
            result_id = result.id if hasattr(result, 'id') else 'unknown'
            print(f"Migrated website smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping website smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to migrate website smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = WebsiteAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.update_website_alert_config(id=target_id, website_alert_config=sdk_config)
            result_id = result.id if (result and hasattr(result, 'id')) else target_id
            print(f"Updated website smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping website smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to update website smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        self._strip_common_metadata(formatted)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap websiteId to the corresponding target website ID.
        src_website_id: Optional[str] = formatted.get('websiteId')
        if src_website_id:
            if src_website_id in self.website_id_map:
                formatted['websiteId'] = self.website_id_map[src_website_id]
            elif self._website_map_fetched and validate:
                raise ValueError(
                    f"websiteId '{src_website_id}' not found in target — "
                    "ensure the website exists in the target system before migrating smart alerts"
                )

        return formatted

    def _get_website_id_map(self) -> Dict[str, str]:
        website_id_map: Dict[str, str] = {}
        try:
            source_websites: List[Dict[str, Any]] = []
            website_endpoint = '/api/website-monitoring/config'

            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}{website_endpoint}",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if response.status_code == 200:
                        source_websites = response.json()
            else:
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
                if sw_name and sw_id and sw_name in target_by_name:
                    website_id_map[str(sw_id)] = target_by_name[str(sw_name)]

            self._website_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build website ID map: {e}")

        return website_id_map
