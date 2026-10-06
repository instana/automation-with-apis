import copy
import json
import requests
from typing import Dict, List, Any, Optional
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator
from instana_client.api.application_alert_configuration_api import ApplicationAlertConfigurationApi
from instana_client.models.application_alert_config import ApplicationAlertConfig
from instana_client.exceptions import ApiException

_API_ENDPOINT = "/api/events/settings/application-alert-configs"


class ApplicationSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "application smart alert"
    api_class = ApplicationAlertConfigurationApi
    required_permissions = ["canConfigureApplicationSmartAlerts"]

    def __init__(self, config: Config):
        super().__init__(config)
        self.application_id_map: Dict[str, str] = {}
        self.application_name_map: Dict[str, str] = {}
        self._application_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.application_id_map = self._get_application_id_map()

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
            print(f"Migrated application smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping application smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to migrate application smart alert configuration '{config_name}'")
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
            print(f"Updated application smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping application smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to update application smart alert configuration '{config_name}'")
            print(f"Error: {e}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True, target_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        formatted = copy.deepcopy(config)
        self._strip_common_metadata(formatted)

        # Strip server-managed field from nested threshold object
        if isinstance(formatted.get('threshold'), dict):
            formatted['threshold'].pop('lastUpdated', None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        self._remap_alert_channels(formatted, validate=validate)

        # Remap applicationId (top-level) to target ID.
        src_app_id: Optional[str] = formatted.get('applicationId')
        if src_app_id:
            if src_app_id in self.application_id_map:
                formatted['applicationId'] = self.application_id_map[src_app_id]
            elif not self._application_map_fetched:
                # Source apps not fetched (file mode without source token).
                # Use applicationId from the existing target config.
                if target_config and target_config.get('applicationId'):
                    formatted['applicationId'] = target_config['applicationId']
                elif validate:
                    raise ValueError(
                        f"cannot remap applicationId '{src_app_id}' — "
                        "provide --source-token and --source-url so the application ID map can be built"
                    )
            elif validate:
                src_app_name = self.application_name_map.get(src_app_id, src_app_id)
                raise ValueError(
                    f"application '{src_app_name}' not found in target — "
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
                    # File mode: use target applications dict from existing target config.
                    if target_config and isinstance(target_config.get('applications'), dict):
                        remapped_apps = target_config['applications']
                    else:
                        remapped_apps[app_id] = app_node
                    break
                else:
                    unmatched_apps.append(app_id)
            if unmatched_apps and validate:
                unmatched_names = [self.application_name_map.get(i, i) for i in unmatched_apps]
                raise ValueError(
                    f"{len(unmatched_names)} application(s) not found in target "
                    f"and cannot be remapped: {unmatched_names}. Ensure the "
                    "application(s) exist in the target system before migrating."
                )
            formatted['applications'] = remapped_apps

        return formatted

    def _get_application_id_map(self) -> Dict[str, str]:
        application_id_map: Dict[str, str] = {}
        try:
            source_apps: List[Dict[str, Any]] = []
            source_fetched = False
            app_endpoint = '/api/application-monitoring/settings/application'

            if self.config.source_url and self.config.source_token:
                response = requests.get(
                    f"{self.config.source_url}{app_endpoint}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_apps = response.json()
                    source_fetched = True

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
                if sa_id and sa_key:
                    self.application_name_map[str(sa_id)] = str(sa_key)
                if sa_key and sa_id and str(sa_key) in target_by_name:
                    application_id_map[str(sa_id)] = target_by_name[str(sa_key)]

            # Only mark as fetched when source apps were actually retrieved from the
            # API. When sourcing from a file, source_url/source_token are absent so
            # source_apps stays empty; leaving _application_map_fetched=False tells
            # _format_config_for_api to skip ID-remapping validation rather than
            # raising ValueError for every config.
            if source_fetched:
                self._application_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build application ID map: {e}")

        return application_id_map
