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
from instana_client.models.mobile_app_alert_config import MobileAppAlertConfig
from instana_client.exceptions import ApiException

_API_ENDPOINT = "/api/events/settings/mobile-app-alert-configs"


class MobileAppSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "mobile app smart alert"
    api_class = EventSettingsApi
    required_permissions = ["canConfigureEventsAndAlerts", "canConfigureMobileAppSmartAlerts"]

    def __init__(self, config: Config):
        super().__init__(config)
        self.mobile_app_id_map: Dict[str, str] = {}
        self.mobile_app_name_map: Dict[str, str] = {}
        self._mobile_map_fetched = False
        self._target_mobile_app_by_name: Dict[str, str] = {}

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.mobile_app_id_map = self._get_mobile_app_id_map()

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
            print(f"Migrated mobile app smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping mobile app smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to migrate mobile app smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str, target_config: Optional[Dict[str, Any]] = None) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config, target_config=target_config)
            response = requests.post(
                f"{self.config.target_url}{_API_ENDPOINT}/{target_id}",
                json=payload,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            result_id = response.json().get('id', target_id)
            print(f"Updated mobile app smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping mobile app smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to update mobile app smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True, target_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        formatted = self._coerce_tag_filter_values(formatted)
        self._strip_common_metadata(formatted)

        if isinstance(formatted.get('threshold'), dict):
            formatted['threshold'].pop('lastUpdated', None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap mobileAppId to the corresponding target mobile app ID.
        src_mobile_app_id: Optional[str] = formatted.get('mobileAppId')
        if src_mobile_app_id:
            if src_mobile_app_id in self.mobile_app_id_map:
                formatted['mobileAppId'] = self.mobile_app_id_map[src_mobile_app_id]
            elif not self._mobile_map_fetched:
                # Source mobile apps were not fetched (file mode without source token).
                # Use the mobileAppId from the existing target config if available —
                # it is the correct target-side ID for this alert.
                if target_config and target_config.get('mobileAppId'):
                    formatted['mobileAppId'] = target_config['mobileAppId']
                elif validate:
                    raise ValueError(
                        f"cannot remap mobileAppId '{src_mobile_app_id}' — "
                        "provide --source-token and --source-url so the mobile app ID map can be built"
                    )
            elif validate:
                src_mobile_app_name = self.mobile_app_name_map.get(src_mobile_app_id, src_mobile_app_id)
                raise ValueError(
                    f"mobile app '{src_mobile_app_name}' not found in target — "
                    "ensure the mobile app exists in the target system before migrating smart alerts"
                )

        return formatted

    def _get_mobile_app_id_map(self) -> Dict[str, str]:
        mobile_app_id_map: Dict[str, str] = {}
        try:
            source_mobile_apps: List[Dict[str, Any]] = []
            source_fetched = False
            mobile_app_endpoint = '/api/mobile-app-monitoring/config'

            if self.config.source_url and self.config.source_token:
                response = requests.get(
                    f"{self.config.source_url}{mobile_app_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_mobile_apps = response.json()
                    source_fetched = True

            response = requests.get(
                f"{self.config.target_url}{mobile_app_endpoint}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_mobile_apps = response.json() if response.status_code == 200 else []

            target_by_name: Dict[str, str] = {
                str(m['name']): str(m['id'])
                for m in target_mobile_apps
                if m.get('name') and m.get('id')
            }
            self._target_mobile_app_by_name = target_by_name
            for sm in source_mobile_apps:
                sm_name = sm.get('name')
                sm_id = sm.get('id')
                if sm_id and sm_name:
                    self.mobile_app_name_map[str(sm_id)] = str(sm_name)
                if sm_name and sm_id and sm_name in target_by_name:
                    mobile_app_id_map[str(sm_id)] = target_by_name[str(sm_name)]

            if source_fetched:
                self._mobile_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build mobile app ID map: {e}")

        return mobile_app_id_map
