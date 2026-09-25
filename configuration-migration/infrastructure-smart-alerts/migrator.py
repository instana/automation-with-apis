import copy
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator
from utils import build_api

from instana_client.api.infrastructure_alert_configuration_api import InfrastructureAlertConfigurationApi
from instana_client.models.infra_alert_config import InfraAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> InfrastructureAlertConfigurationApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, InfrastructureAlertConfigurationApi)


class InfrastructureSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "infrastructure smart alert"
    api_class = InfrastructureAlertConfigurationApi
    model_class = InfraAlertConfig

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.source_url, self.config.source_token)
            results = api.find_active_infra_alert_configs()
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving source alert configurations from API: {e}")
            return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            results = api.find_active_infra_alert_configs()
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = InfraAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.create_infra_alert_config(sdk_config)
            result_id = result.id if hasattr(result, 'id') else 'unknown'
            print(f"Migrated infrastructure smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping infrastructure smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to migrate infrastructure smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = InfraAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.update_infra_alert_config(id=target_id, infra_alert_config=sdk_config)
            result_id = result.id if (result and hasattr(result, 'id')) else target_id
            print(f"Updated infrastructure smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping infrastructure smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to update infrastructure smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        formatted = self._coerce_tag_filter_values(formatted)
        self._strip_common_metadata(formatted)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        formatted.setdefault('groupBy', [])
        self._remap_alert_channels(formatted, validate=validate)

        return formatted
