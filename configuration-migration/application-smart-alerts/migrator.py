import copy
import requests
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator
from utils import build_api

from instana_client.api.application_alert_configuration_api import ApplicationAlertConfigurationApi
from instana_client.models.application_alert_config import ApplicationAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> ApplicationAlertConfigurationApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, ApplicationAlertConfigurationApi)


class ApplicationSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "application smart alert"
    api_class = ApplicationAlertConfigurationApi
    model_class = ApplicationAlertConfig

    def __init__(self, config: Config):
        super().__init__(config)
        self.event_id_map: Dict[str, str] = {}
        self.application_id_map: Dict[str, str] = {}
        self._event_map_fetched = False
        self._application_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.event_id_map = self._get_event_id_map()
        self.application_id_map = self._get_application_id_map()

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.source_url, self.config.source_token)
            results = api.find_all_active_application_alert_configs(application_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving source alert configurations from API: {e}")
            return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            results = api.find_all_active_application_alert_configs(application_id=None)
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = ApplicationAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.create_application_alert_config(sdk_config)
            result_id = result.id if hasattr(result, 'id') else 'unknown'
            print(f"Migrated application smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping application smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to migrate application smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        try:
            payload = self._format_config_for_api(config)
            sdk_config = ApplicationAlertConfig.from_dict(payload)
            api = self._get_sdk_client(self.config.target_url, self.config.target_token)
            result = api.update_application_alert_config(id=target_id, application_alert_config=sdk_config)
            result_id = result.id if (result and hasattr(result, 'id')) else target_id
            print(f"Updated application smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping application smart alert configuration '{config_name}': {e}")
            return None
        except ApiException as e:
            print(f"Failed to update application smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        self._strip_common_metadata(formatted)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap applicationId (top-level) to target ID.
        src_app_id: Optional[str] = formatted.get('applicationId')
        if src_app_id:
            if src_app_id in self.application_id_map:
                formatted['applicationId'] = self.application_id_map[src_app_id]
            elif self._application_map_fetched and validate:
                raise ValueError(
                    f"applicationId '{src_app_id}' not found in target — "
                    "ensure the application exists in the target system"
                )

        # Remap the 'applications' dict keys and nested applicationId values.
        if isinstance(formatted.get('applications'), dict) and formatted['applications']:
            remapped_apps: Dict[str, Any] = {}
            unmatched_apps: List[str] = []
            for app_id, app_node in formatted['applications'].items():
                if app_id in self.application_id_map:
                    tgt_app_id = self.application_id_map[app_id]
                    node = copy.deepcopy(app_node) if isinstance(app_node, dict) else app_node
                    if isinstance(node, dict):
                        node['applicationId'] = tgt_app_id
                    remapped_apps[tgt_app_id] = node
                elif not self._application_map_fetched:
                    remapped_apps[app_id] = app_node
                else:
                    unmatched_apps.append(app_id)
            if unmatched_apps and validate:
                raise ValueError(
                    f"{len(unmatched_apps)} application(s) not found in target "
                    f"and cannot be remapped: {unmatched_apps}. Ensure the "
                    "application(s) exist in the target system before migrating."
                )
            formatted['applications'] = remapped_apps

        return formatted

    def _get_event_id_map(self) -> Dict[str, str]:
        event_id_map: Dict[str, str] = {}
        try:
            source_events: List[Dict[str, Any]] = []
            events_endpoint = '/api/events/settings/event-specifications/custom'

            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}{events_endpoint}",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if response.status_code == 200:
                        source_events = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}{events_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_events = response.json()

            response = requests.get(
                f"{self.config.target_url}{events_endpoint}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_events = response.json() if response.status_code == 200 else []

            target_by_name: Dict[str, str] = {
                str(e['name']): str(e['id'])
                for e in target_events
                if e.get('name') and e.get('id')
            }
            for se in source_events:
                se_name = se.get('name')
                se_id = se.get('id')
                if se_name and se_id and se_name in target_by_name:
                    event_id_map[str(se_id)] = target_by_name[str(se_name)]

            self._event_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build custom event specifications ID map: {e}")

        return event_id_map

    def _get_application_id_map(self) -> Dict[str, str]:
        application_id_map: Dict[str, str] = {}
        try:
            source_apps: List[Dict[str, Any]] = []
            app_endpoint = '/api/application-monitoring/settings/application'

            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}{app_endpoint}",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if response.status_code == 200:
                        source_apps = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}{app_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_apps = response.json()

            response = requests.get(
                f"{self.config.target_url}{app_endpoint}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_apps = response.json() if response.status_code == 200 else []

            target_by_name: Dict[str, str] = {}
            for a in target_apps:
                key = a.get('label') or a.get('name')
                if key and a.get('id'):
                    target_by_name[str(key)] = str(a['id'])

            for sa in source_apps:
                sa_key = sa.get('label') or sa.get('name')
                sa_id = sa.get('id')
                if sa_key and sa_id and str(sa_key) in target_by_name:
                    application_id_map[str(sa_id)] = target_by_name[str(sa_key)]

            self._application_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build application ID map: {e}")

        return application_id_map
