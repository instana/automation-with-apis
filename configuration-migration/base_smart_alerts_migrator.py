"""Base class for Smart Alert migrators (Application, Website, Mobile App, Infrastructure)."""

import copy
import json
import requests
import urllib3
from typing import Dict, List, Any, Optional, Type
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "."))
from config import Config
from utils import build_api
from instana_client.exceptions import ApiException


class BaseSmartAlertsMigrator:
    """Base class providing common migration lifecycle, duplicate handling, and channel mapping."""

    entity_type_name: str = "smart alert"
    api_class: Optional[Type[Any]] = None
    model_class: Optional[Type[Any]] = None

    def __init__(self, config: Config):
        self.config = config
        self.channel_id_map: Dict[str, str] = {}
        self._channel_map_fetched = False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        """Execute the migration workflow for smart alert configurations."""
        self.config.validate()

        self._init_resource_maps()

        print(f"Starting migration of {self.entity_type_name} configurations...")

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

        name_decision_cache: Dict[str, str] = {}

        for config in source_configs:
            config_name = config.get('name')
            if not config_name:
                continue

            source_id = config.get('id')
            target_config = target_by_id.get(source_id) if source_id else None
            if target_config is None and config_name in target_config_names:
                target_config = next((c for c in target_configs if c.get('name') == config_name), None)

            if target_config:
                if self._configs_are_equal(config, target_config):
                    print(f"Skipping {self.entity_type_name} configuration '{config_name}' - identical in target")
                    skipped_identical += 1
                    continue

                if getattr(self.config, 'on_duplicate', None) in ['skip', 'update', 'cancel']:
                    choice = self.config.on_duplicate
                else:
                    choice = name_decision_cache.get(config_name)
                    if choice is None:
                        choice = self._prompt_for_duplicate_config(str(config_name))
                        name_decision_cache[config_name] = choice

                if choice == 'skip':
                    print(f"Skipping {self.entity_type_name} configuration '{config_name}' - already exists in target system")
                    skipped_user += 1
                    continue
                elif choice == 'update':
                    print(f"Updating {self.entity_type_name} configuration '{config_name}' - already exists in target system")
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
        print(f"Migration complete. Found {source_count} source {self.entity_type_name} configurations, "
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

    def _init_resource_maps(self) -> None:
        """Hook for subclasses to fetch dependent ID maps."""
        self.channel_id_map = self._get_channel_id_map()

    def _get_sdk_client(self, url: str, token: str) -> Any:
        """Create an SDK API client instance for this migrator."""
        if not self.api_class:
            raise NotImplementedError("Subclasses must define api_class or override _get_sdk_client")
        return build_api(url, token, self.config.verify_ssl, self.api_class)

    def _get_source_configs(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch source configurations from file or API."""
        if self.config.events_source == "file":
            try:
                with open(self.config.events_file_path, 'r') as f:
                    configs = json.load(f)
                return configs
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                return None
        return self._fetch_source_configs_from_api()

    def _fetch_source_configs_from_api(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch configurations from source Instana backend."""
        raise NotImplementedError("Subclasses must implement _fetch_source_configs_from_api")

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch configurations from target Instana backend."""
        raise NotImplementedError("Subclasses must implement _get_target_configs")

    def _create_config(self, config: Dict[str, Any], config_name: str) -> Optional[bool]:
        """Create a single configuration in the target backend."""
        raise NotImplementedError("Subclasses must implement _create_config")

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> Optional[bool]:
        """Update an existing configuration in the target backend."""
        raise NotImplementedError("Subclasses must implement _update_config")

    def _prompt_for_duplicate_config(self, config_name: str) -> str:
        """Prompt user for duplicate resolution."""
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

    def _coerce_tag_filter_values(self, obj: Any) -> Any:
        """Recursively coerce numeric 'value' fields inside TAG_FILTER nodes to strings."""
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

    def _strip_common_metadata(self, formatted: Dict[str, Any]) -> None:
        """Remove read-only/server-managed fields."""
        read_only_fields = [
            'id', 'created', 'initialCreated', 'lastUpdated', 'invalid',
            'readOnly', 'enabled', 'alertChannelNames', 'websiteName',
            'mobileAppName', 'applicationNames'
        ]
        for field in read_only_fields:
            formatted.pop(field, None)

    def _remap_alert_channels(self, formatted: Dict[str, Any], validate: bool = True) -> None:
        """Remap alertChannelIds list and alertChannels dict in formatted config."""
        formatted.setdefault('alertChannelIds', [])
        formatted.setdefault('customPayloadFields', [])

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
                print(f"  Warning: '{formatted.get('name')}' — {len(unmatched)} alertChannelId(s) not found in "
                      f"target and will be omitted: {unmatched}")
            formatted['alertChannelIds'] = remapped

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
            'readOnly', 'enabled', 'alertChannelNames', 'alertChannelIds',
            'alertChannels', 'applicationId', 'applications', 'websiteId',
            'websiteName', 'mobileAppId', 'mobileAppName', 'applicationNames'
        }

        src_content = {k: v for k, v in src_norm.items() if k not in exclude_fields}
        tgt_content = {k: v for k, v in tgt_norm.items() if k not in exclude_fields}

        return src_content == tgt_content

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        """Prepare a config dict for submission via the SDK."""
        raise NotImplementedError("Subclasses must implement _format_config_for_api")
