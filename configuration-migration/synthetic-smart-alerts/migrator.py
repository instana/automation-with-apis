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

_API_ENDPOINT = "/api/events/settings/global-alert-configs/synthetics"
_SYNTHETIC_TESTS_ENDPOINT = "/api/synthetics/settings/tests"


class SyntheticSmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "synthetic smart alert"
    api_class = EventSettingsApi
    required_permissions = ["canConfigureGlobalSyntheticSmartAlerts"]

    def __init__(self, config: Config):
        super().__init__(config)
        self.synthetic_test_id_map: Dict[str, str] = {}
        self.synthetic_test_name_map: Dict[str, str] = {}
        self._synthetic_test_map_fetched = False

    def _init_resource_maps(self) -> None:
        super()._init_resource_maps()
        self.synthetic_test_id_map = self._get_synthetic_test_id_map()

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
            print(f"Migrated synthetic smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping synthetic smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to migrate synthetic smart alert configuration '{config_name}'")
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
            print(f"Updated synthetic smart alert configuration '{config_name}' (Target ID: {result_id})")
            return True
        except ValueError as e:
            print(f"Skipping synthetic smart alert configuration '{config_name}': {e}")
            return None
        except requests.RequestException as e:
            print(f"Failed to update synthetic smart alert configuration '{config_name}'")
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

        # Remap syntheticTestIds
        src_test_ids: Optional[List[str]] = formatted.get('syntheticTestIds')
        if src_test_ids and isinstance(src_test_ids, list):
            remapped_test_ids = []
            unmatched_test_ids = []
            for test_id in src_test_ids:
                if test_id in self.synthetic_test_id_map:
                    remapped_test_ids.append(self.synthetic_test_id_map[test_id])
                elif not self._synthetic_test_map_fetched:
                    # In file mode without source token, fallback to target_config's syntheticTestIds if available
                    if target_config and target_config.get('syntheticTestIds'):
                        remapped_test_ids = target_config['syntheticTestIds']
                        break
                    elif validate:
                        raise ValueError(
                            f"cannot remap synthetic test ID '{test_id}' — "
                            "provide --source-token and --source-url so the synthetic test ID map can be built"
                        )
                    else:
                        remapped_test_ids.append(test_id)
                elif validate:
                    test_label = self.synthetic_test_name_map.get(test_id, test_id)
                    unmatched_test_ids.append(f"'{test_label}'")
                else:
                    remapped_test_ids.append(test_id)

            if unmatched_test_ids and validate:
                tests_str = ", ".join(unmatched_test_ids)
                raise ValueError(
                    f"synthetic test(s) {tests_str} not found in target — "
                    "ensure the synthetic tests exist in the target system"
                )

            formatted['syntheticTestIds'] = remapped_test_ids

        return formatted

    def _get_synthetic_test_id_map(self) -> Dict[str, str]:
        test_id_map: Dict[str, str] = {}
        try:
            source_tests: List[Dict[str, Any]] = []
            source_fetched = False

            if self.config.source_token and self.config.source_url:
                try:
                    src_resp = requests.get(
                        f"{self.config.source_url}{_SYNTHETIC_TESTS_ENDPOINT}",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if src_resp.status_code == 200:
                        source_tests = src_resp.json()
                        source_fetched = True
                except requests.RequestException:
                    pass

            tgt_resp = requests.get(
                f"{self.config.target_url}{_SYNTHETIC_TESTS_ENDPOINT}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_tests: List[Dict[str, Any]] = tgt_resp.json() if tgt_resp.status_code == 200 else []

            target_by_label: Dict[str, str] = {
                str(t['label']): str(t['id'])
                for t in target_tests
                if t.get('label') and t.get('id')
            }
            for src_test in source_tests:
                src_id = src_test.get('id')
                src_label = src_test.get('label')
                if src_id and src_label:
                    self.synthetic_test_name_map[str(src_id)] = str(src_label)
                    if str(src_label) in target_by_label:
                        test_id_map[str(src_id)] = target_by_label[str(src_label)]

            if source_fetched:
                self._synthetic_test_map_fetched = True
        except Exception as e:
            print(f"Warning: Failed to fetch synthetic tests for ID mapping: {e}")

        return test_id_map
