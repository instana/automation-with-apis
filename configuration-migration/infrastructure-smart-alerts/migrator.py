import copy
import json
import requests
import urllib3
from typing import Dict, List, Any, Optional
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from utils import build_api

from instana_client.api.infrastructure_alert_configuration_api import InfrastructureAlertConfigurationApi
from instana_client.models.infra_alert_config import InfraAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> InfrastructureAlertConfigurationApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, InfrastructureAlertConfigurationApi)


class InfrastructureSmartAlertsMigrator:
    def __init__(self, config: Config):
        self.config = config
        self.channel_id_map: Dict[str, str] = {}
        self._channel_map_fetched = False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        self.config.validate()

        self.channel_id_map = self._get_channel_id_map()

        print("Starting migration of infrastructure smart alert configurations...")

        source_configs = self._get_source_configs()
        if source_configs is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

        target_configs = self._get_target_configs()
        if target_configs is None:
            return {"source": len(source_configs), "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

        target_by_id = {c.get('id'): c for c in target_configs if c.get('id')}
        target_config_names = {c.get('name') for c in target_configs if c.get('name')}

        migrated_count = 0
        updated_count = 0
        skipped_identical = 0
        skipped_user = 0
        skipped_invalid = 0
        failed_count = 0

        # Cache per-name duplicate decisions so the prompt only fires once when
        # multiple source configs share the same name.
        name_decision_cache: Dict[str, str] = {}

        for config in source_configs:
            config_name = config.get('name')
            if not config_name:
                continue

            # Match by ID first — only fall back to name-matching on first-time migration.
            source_id = config.get('id')
            target_config = target_by_id.get(source_id) if source_id else None
            if target_config is None and config_name in target_config_names:
                target_config = next((c for c in target_configs if c.get('name') == config_name), None)

            if target_config:
                if self._configs_are_equal(config, target_config):
                    print(f"Skipping infrastructure smart alert configuration '{config_name}' - identical in target")
                    skipped_identical += 1
                    continue

                # Check configured on_duplicate setting or prompt user
                if self.config.on_duplicate in ['skip', 'update', 'cancel']:
                    choice = self.config.on_duplicate
                else:
                    # Reuse a previous decision for this name if one was already made.
                    choice = name_decision_cache.get(config_name)
                    if choice is None:
                        choice = self._prompt_for_duplicate_config(str(config_name))
                        name_decision_cache[config_name] = choice

                if choice == 'skip':
                    print(f"Skipping infrastructure smart alert configuration '{config_name}' - already exists in target system")
                    skipped_user += 1
                    continue
                elif choice == 'update':
                    print(f"Updating infrastructure smart alert configuration '{config_name}' - already exists in target system")
                    result = self._update_config(config, target_config.get('id'), str(config_name))
                    if result is True:
                        updated_count += 1
                    elif result is None:
                        skipped_invalid += 1
                    else:
                        failed_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break

            result = self._create_config(config, str(config_name))
            if result is True:
                migrated_count += 1
            elif result is None:
                skipped_invalid += 1
            else:
                failed_count += 1

        source_count = len(source_configs)
        skipped_total = skipped_identical + skipped_user + skipped_invalid
        print(f"Migration complete. Found {source_count} source infrastructure smart alert configurations, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_total} ({skipped_identical} identical, "
              f"{skipped_user} user skipped, {skipped_invalid} invalid), "
              f"failed {failed_count}.")

        return {
            "source": source_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped_identical": skipped_identical,
            "skipped_user": skipped_user,
            "skipped_invalid": skipped_invalid,
            "failed": failed_count,
        }

    def _get_source_configs(self) -> Optional[List[Dict[str, Any]]]:
        if self.config.events_source == "file":
            try:
                with open(self.config.events_file_path, 'r') as f:
                    configs = json.load(f)
                return configs
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                return None
        else:
            try:
                api = _build_sdk_client(
                    self.config.source_url,
                    self.config.source_token,
                    self.config.verify_ssl,
                )
                results = api.find_active_infra_alert_configs()
                return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
            except ApiException as e:
                print(f"Error retrieving source alert configurations from API: {e}")
                return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            api = _build_sdk_client(
                self.config.target_url,
                self.config.target_token,
                self.config.verify_ssl,
            )
            results = api.find_active_infra_alert_configs()
            return [r.to_dict() if hasattr(r, 'to_dict') else r for r in results]
        except ApiException as e:
            print(f"Error retrieving target alert configurations: {e}")
            return None

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

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        """Returns True on success, None on validation skip, False on API error."""
        try:
            payload = self._format_config_for_api(config)
            sdk_config = InfraAlertConfig.from_dict(payload)
            api = _build_sdk_client(
                self.config.target_url,
                self.config.target_token,
                self.config.verify_ssl,
            )
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
        """Returns True on success, None on validation skip, False on API error."""
        try:
            payload = self._format_config_for_api(config)
            sdk_config = InfraAlertConfig.from_dict(payload)
            api = _build_sdk_client(
                self.config.target_url,
                self.config.target_token,
                self.config.verify_ssl,
            )
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

    def _coerce_tag_filter_values(self, obj: Any) -> Any:
        """Recursively coerce numeric 'value' fields inside TAG_FILTER nodes to strings.

        The SDK's TagFilterAllOfValue oneOf validator fails when a value is an
        int because int satisfies multiple schemas, producing a 'Multiple matches found' error.
        """
        if isinstance(obj, list):
            return [self._coerce_tag_filter_values(item) for item in obj]
        if isinstance(obj, dict):
            coerce = obj.get('type') == 'TAG_FILTER'
            result = {}
            for k, v in obj.items():
                if coerce and k == 'value' and isinstance(v, (int, float)) and not isinstance(v, bool):
                    result[k] = str(v)
                else:
                    result[k] = self._coerce_tag_filter_values(v)
            return result
        return obj

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        """Prepare a source config dict for submission via the SDK.

        Strips read-only/server-only fields and remaps cross-system IDs.
        """
        formatted = copy.deepcopy(config)

        # Coerce numeric tag filter values to strings to avoid oneOf ambiguity
        formatted = self._coerce_tag_filter_values(formatted)

        # Remove read-only/server-managed fields that must not be sent in API requests.
        read_only_fields = [
            'id', 'created', 'initialCreated', 'lastUpdated', 'invalid',
            'readOnly', 'enabled', 'alertChannelNames',
        ]
        for field in read_only_fields:
            formatted.pop(field, None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        # Ensure required list fields are present.
        formatted.setdefault('alertChannelIds', [])
        formatted.setdefault('customPayloadFields', [])
        formatted.setdefault('groupBy', [])

        # Remap alertChannelIds to target IDs.
        if isinstance(formatted.get('alertChannelIds'), list):
            remapped = []
            unmatched = []
            for item in formatted['alertChannelIds']:
                if item in self.channel_id_map:
                    remapped.append(self.channel_id_map[item])
                elif not self._channel_map_fetched:
                    remapped.append(item)
                else:
                    unmatched.append(item)
            if unmatched and validate:
                print(f"  Warning: '{formatted['name']}' — {len(unmatched)} alertChannelId(s) not found in "
                      f"target and will be omitted: {unmatched}")
            formatted['alertChannelIds'] = remapped

        # Remap alertChannels dict if present (mapping severity -> list of channel IDs)
        if isinstance(formatted.get('alertChannels'), dict):
            remapped_alert_channels = {}
            for sev, ch_ids in formatted['alertChannels'].items():
                if isinstance(ch_ids, list):
                    sev_remapped = []
                    for item in ch_ids:
                        if item in self.channel_id_map:
                            sev_remapped.append(self.channel_id_map[item])
                        elif not self._channel_map_fetched:
                            sev_remapped.append(item)
                    remapped_alert_channels[sev] = sev_remapped
                else:
                    remapped_alert_channels[sev] = ch_ids
            formatted['alertChannels'] = remapped_alert_channels

        return formatted

    def _get_channel_id_map(self) -> Dict[str, str]:
        """Build a source-ID → target-ID map for alerting channels."""
        channel_id_map: Dict[str, str] = {}
        try:
            source_channels: List[Dict[str, Any]] = []

            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}/api/events/settings/alertingChannels",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl,
                    )
                    if response.status_code == 200:
                        source_channels = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}/api/events/settings/alertingChannels",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 200:
                    source_channels = response.json()

            response = requests.get(
                f"{self.config.target_url}/api/events/settings/alertingChannels",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            target_channels = response.json() if response.status_code == 200 else []

            target_by_name: Dict[str, str] = {
                str(c['name']): str(c['id'])
                for c in target_channels
                if c.get('name') and c.get('id')
            }
            for sc in source_channels:
                sc_name = sc.get('name')
                sc_id = sc.get('id')
                if sc_name and sc_id and sc_name in target_by_name:
                    channel_id_map[str(sc_id)] = target_by_name[str(sc_name)]

            self._channel_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build alerting channels ID map: {e}")

        return channel_id_map

    def _configs_are_equal(self, source: Dict[str, Any], target: Dict[str, Any]) -> bool:
        """Compare source and target configs for equality, ignoring IDs and metadata."""
        try:
            src_norm = self._format_config_for_api(source, validate=False)
            tgt_norm = self._format_config_for_api(target, validate=False)
        except ValueError:
            return False

        exclude_fields = {
            'id', 'created', 'initialCreated', 'lastUpdated', 'invalid',
            'readOnly', 'enabled', 'alertChannelNames', 'alertChannelIds', 'alertChannels',
        }

        src_content = {k: v for k, v in src_norm.items() if k not in exclude_fields}
        tgt_content = {k: v for k, v in tgt_norm.items() if k not in exclude_fields}

        return src_content == tgt_content
