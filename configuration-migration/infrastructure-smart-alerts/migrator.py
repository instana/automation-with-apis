import copy
import json
import requests
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator

from instana_client.api.infrastructure_alert_configuration_api import InfrastructureAlertConfigurationApi
from instana_client.models.infra_alert_config import InfraAlertConfig
from instana_client.exceptions import ApiException

_API_ENDPOINT = "/api/events/settings/infra-alert-configs"


class InfrastructureSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "infrastructure smart alert"
    api_class = InfrastructureAlertConfigurationApi
    required_permissions = ["canConfigureGlobalInfraSmartAlerts"]

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
            print(f"Migrated infrastructure smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping infrastructure smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to migrate infrastructure smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str, target_config: Optional[Dict[str, Any]] = None) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            response = requests.post(
                f"{self.config.target_url}{_API_ENDPOINT}/{target_id}",
                json=payload,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            result_id = response.json().get('id', target_id)
            print(f"Updated infrastructure smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping infrastructure smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to update infrastructure smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        formatted = self._coerce_tag_filter_values(formatted)
        self._strip_common_metadata(formatted)

        if isinstance(formatted.get('threshold'), dict):
            formatted['threshold'].pop('lastUpdated', None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        formatted.setdefault('groupBy', [])
        self._remap_alert_channels(formatted, validate=validate)

        return formatted
