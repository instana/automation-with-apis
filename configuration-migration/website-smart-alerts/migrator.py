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

from instana_client.api.event_settings_api import EventSettingsApi
from instana_client.models.website_alert_config import WebsiteAlertConfig
from instana_client.exceptions import ApiException


def _build_sdk_client(url: str, token: str, verify_ssl: bool) -> EventSettingsApi:
    """Create an SDK API client for the given Instana backend."""
    return build_api(url, token, verify_ssl, EventSettingsApi)


class WebsiteSmartAlertsMigrator:
    def __init__(self, config: Config):
        self.config = config
        self.channel_id_map: Dict[str, str] = {}
        self.website_id_map: Dict[str, str] = {}
        self._channel_map_fetched = False
        self._website_map_fetched = False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        self.config.validate()

        self.channel_id_map = self._get_channel_id_map()
        self.website_id_map = self._get_website_id_map()

        print("Starting migration of website smart alert configurations...")

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
                    print(f"Skipping website smart alert configuration '{config_name}' - identical in target")
                    skipped_identical += 1
                    continue

                # Reuse a previous decision for this name if one was already made.
                choice = name_decision_cache.get(config_name)
                if choice is None:
                    choice = self._prompt_for_duplicate_config(str(config_name))
                    name_decision_cache[config_name] = choice

                if choice == 'skip':
                    print(f"Skipping website smart alert configuration '{config_name}' - already exists in target system")
                    skipped_user += 1
                    continue
                elif choice == 'update':
                    print(f"Updating website smart alert configuration '{config_name}' - already exists in target system")
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
        print(f"Migration complete. Found {source_count} source website smart alert configurations, "
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
                results = api.find_active_website_alert_configs(website_id=None)
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
            results = api.find_active_website_alert_configs(website_id=None)
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
            sdk_config = WebsiteAlertConfig.from_dict(payload)
            api = _build_sdk_client(
                self.config.target_url,
                self.config.target_token,
                self.config.verify_ssl,
            )
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
        """Returns True on success, None on validation skip, False on API error."""
        try:
            payload = self._format_config_for_api(config)
            sdk_config = WebsiteAlertConfig.from_dict(payload)
            api = _build_sdk_client(
                self.config.target_url,
                self.config.target_token,
                self.config.verify_ssl,
            )
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
        """Prepare a source config dict for submission via the SDK.

        Strips read-only/server-only fields, remaps cross-system IDs, and
        validates that a websiteId is present and mappable.
        """
        formatted = copy.deepcopy(config)

        # Remove read-only fields that must not be sent in API requests.
        read_only_fields = [
            'id', 'created', 'lastUpdated', 'invalid', 'readOnly',
            'alertChannelNames', 'websiteName', 'initialCreated',
        ]
        for field in read_only_fields:
            formatted.pop(field, None)

        if 'name' not in formatted:
            raise ValueError("Alert configuration must have a 'name' field")

        # Ensure required list fields are present.
        formatted.setdefault('alertChannelIds', [])
        formatted.setdefault('customPayloadFields', [])

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

    def _get_website_id_map(self) -> Dict[str, str]:
        """Build a source website-ID → target website-ID map by matching on name."""
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

    def _configs_are_equal(self, source: Dict[str, Any], target: Dict[str, Any]) -> bool:
        """Return True if source and target represent the same alert config content.

        Normalizes both configs and compares content-only fields, excluding
        system-assigned fields like id and lastUpdated.
        """
        try:
            src_norm = self._format_config_for_api(source, validate=False)
            tgt_norm = self._format_config_for_api(target, validate=False)
        except ValueError:
            return False

        # Exclude cross-system reference fields and server-managed metadata.
        # websiteId is cross-system (different IDs for the same website) —
        # exclude it to avoid spurious duplicate prompts.
        exclude_fields = {
            'id', 'lastUpdated', 'invalid', 'alertChannelNames', 'websiteName',
            'alertChannelIds', 'websiteId',
        }

        src_content = {k: v for k, v in src_norm.items() if k not in exclude_fields}
        tgt_content = {k: v for k, v in tgt_norm.items() if k not in exclude_fields}

        return src_content == tgt_content
