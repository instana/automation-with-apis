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
from instana_client.models.mobile_app_alert_config import MobileAppAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> EventSettingsApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, EventSettingsApi)


class MobileAppSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "mobile app smart alert"
    api_class = EventSettingsApi
    model_class = MobileAppAlertConfig

    def __init__(self, config: Config):
        super().__init__(config)
        self.mobile_app_id_map: Dict[str, str] = {}
        self._mobile_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.mobile_app_id_map = self._get_mobile_app_id_map()

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.source_url, self.config.source_token)
            results = api.find_active_mobile_app_alert_configs(mobile_app_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving source alert configurations from API: {e}")
            return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            results = api.find_active_mobile_app_alert_configs(mobile_app_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = MobileAppAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.create_mobile_app_alert_config(sdk_config)
            result_id = result.id if hasattr(result, 'id') else 'unknown'
            print(f"Migrated mobile app smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping mobile app smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to migrate mobile app smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = MobileAppAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.update_mobile_app_alert_config(id=target_id, mobile_app_alert_config=sdk_config)
            result_id = result.id if (result and hasattr(result, 'id')) else target_id
            print(f"Updated mobile app smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping mobile app smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to update mobile app smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        formatted = self._coerce_tag_filter_values(formatted)
        self._strip_common_metadata(formatted)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap mobileAppId to the corresponding target mobile app ID.
        src_mobile_app_id: Optional[str] = formatted.get('mobileAppId')
        if src_mobile_app_id:
            if src_mobile_app_id in self.mobile_app_id_map:
                formatted['mobileAppId'] = self.mobile_app_id_map[src_mobile_app_id]
            elif self._mobile_map_fetched and validate:
                raise ValueError(
                    f"mobileAppId '{src_mobile_app_id}' not found in target — "
                    "ensure the mobile app exists in the target system before migrating smart alerts"
                )

        return formatted

    def _get_mobile_app_id_map(self) -> Dict[str, str]:
        mobile_app_id_map: Dict[str, str] = {}
        try:
            source_mobile_apps: List[Dict[str, Any]] = []
            mobile_app_endpoint = '/api/mobile-app-monitoring/config'

            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}{mobile_app_endpoint}",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if response.status_code == 200:
                        source_mobile_apps = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}{mobile_app_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_mobile_apps = response.json()

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
            for sm in source_mobile_apps:
                sm_name = sm.get('name')
                sm_id = sm.get('id')
                if sm_name and sm_id and sm_name in target_by_name:
                    mobile_app_id_map[str(sm_id)] = target_by_name[str(sm_name)]

            self._mobile_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build mobile app ID map: {e}")

        return mobile_app_id_map
