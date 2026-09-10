import json
import uuid
import requests
import urllib3
from typing import Dict, List, Any, Optional
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config


class AlertConfigsMigrator:
    def __init__(self, config: Config):
        self.config = config
        self.req_alert_configs = "/api/events/settings/alerts"
        self.channel_id_map = {}
        self.event_id_map = {}
        self._channel_map_fetched = False
        self._event_map_fetched = False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        self.config.validate()

        self.channel_id_map = self._get_channel_id_map()
        self.event_id_map = self._get_event_id_map()

        print("Starting migration of alert configurations...")

        source_configs = self._get_source_configs()
        if source_configs is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "failed": 0}

        target_configs = self._get_target_configs()
        if target_configs is None:
            return {"source": len(source_configs), "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "failed": 0}

        target_by_id = {c.get('id'): c for c in target_configs if c.get('id')}
        target_config_names = {c.get('alertName') for c in target_configs if c.get('alertName')}

        migrated_count = 0
        updated_count = 0
        skipped_identical = 0
        skipped_user = 0
        failed_count = 0

        for config in source_configs:
            config_name = config.get('alertName')
            if not config_name:
                continue

            # Match by ID first — configs preserve their source ID on PUT, so an ID
            # match is an exact counterpart. Only fall back to name-matching when the
            # source ID isn't present in the target (e.g. first-time migration).
            source_id = config.get('id')
            target_config = target_by_id.get(source_id) if source_id else None
            if target_config is None and config_name in target_config_names:
                target_config = next((c for c in target_configs if c.get('alertName') == config_name), None)

            if target_config:
                if self._configs_are_equal(config, target_config):
                    print(f"Skipping alert configuration '{config_name}' - identical in target")
                    skipped_identical += 1
                    continue

                choice = self._prompt_for_duplicate_config(str(config_name))
                if choice == 'skip':
                    print(f"Skipping alert configuration '{config_name}' - already exists in target system")
                    skipped_user += 1
                    continue
                elif choice == 'update':
                    print(f"Updating alert configuration '{config_name}' - already exists in target system")
                    if self._update_config(config, target_config.get('id'), str(config_name)):
                        updated_count += 1
                    else:
                        failed_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break

            if self._create_config(config, str(config_name)):
                migrated_count += 1
            else:
                failed_count += 1

        source_count = len(source_configs)
        skipped_total = skipped_identical + skipped_user
        print(f"Migration complete. Found {source_count} source alert configurations, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_total} ({skipped_identical} identical, "
              f"{skipped_user} user skipped), "
              f"failed {failed_count}.")

        return {
            "source": source_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped_identical": skipped_identical,
            "skipped_user": skipped_user,
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
                response = requests.get(
                    f"{self.config.source_url}{self.req_alert_configs}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                print(f"Error retrieving source alert configurations from API: {e}")
                return None

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_alert_configs}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
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

    def _create_config(self, config: Dict[str, Any], config_name: str) -> bool:
        try:
            formatted_config = self._format_config_for_api(config)
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_configs}/{formatted_config['id']}",
                json=formatted_config,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            result = response.json()
            print(f"Migrated alert configuration '{config_name}' (Target ID: {result.get('id', 'unknown')})")
            return True
        except ValueError as e:
            print(f"Skipping alert configuration '{config_name}': {e}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to migrate alert configuration '{config_name}'")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"API response: {e.response.text}")
            return False

    def _update_config(self, config: Dict[str, Any], target_id: str, config_name: str) -> bool:
        try:
            formatted_config = self._format_config_for_api(config)
            formatted_config['id'] = target_id
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_configs}/{target_id}",
                json=formatted_config,
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            result = response.json()
            print(f"Updated alert configuration '{config_name}' (Target ID: {result.get('id', 'unknown')})")
            return True
        except ValueError as e:
            print(f"Skipping alert configuration '{config_name}': {e}")
            return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to update alert configuration '{config_name}'")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"API response: {e.response.text}")
            return False

    def _format_config_for_api(self, config: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        formatted = config.copy()
        
        # Remove read-only fields that shouldn't be sent in API requests
        read_only_fields = ['lastUpdated', 'invalid', 'alertChannelNames', 'applicationNames']
        for field in read_only_fields:
            if field in formatted:
                del formatted[field]
        
        # Ensure required fields are present
        if 'id' not in formatted:
            formatted['id'] = str(uuid.uuid4())
        
        if 'alertName' not in formatted:
            raise ValueError("Alert configuration must have an 'alertName' field")
        
        # Ensure eventFilteringConfiguration is properly structured
        if 'eventFilteringConfiguration' not in formatted:
            formatted['eventFilteringConfiguration'] = {
                "query": None,
                "ruleIds": [],
                "eventTypes": [],
                "applicationAlertConfigIds": [],
                "validVersion": 1
            }
        
        # Ensure customPayloadFields is an array
        if 'customPayloadFields' not in formatted:
            formatted['customPayloadFields'] = []
        
        # Ensure integrationIds is an array
        if 'integrationIds' not in formatted:
            formatted['integrationIds'] = []
        
        # Ensure muteUntil has a default value
        if 'muteUntil' not in formatted:
            formatted['muteUntil'] = 0
        
        # Ensure includeEntityNameInLegacyAlerts has a default value
        if 'includeEntityNameInLegacyAlerts' not in formatted:
            formatted['includeEntityNameInLegacyAlerts'] = False
            
        # Remap integrationIds (alert channels) to target IDs dynamically
        if 'integrationIds' in formatted and isinstance(formatted['integrationIds'], list):
            remapped_integrations = []
            unmatched_channels = []
            for item in formatted['integrationIds']:
                if item in self.channel_id_map:
                    remapped_integrations.append(self.channel_id_map[item])
                elif not self._channel_map_fetched:
                    # Map fetch was never attempted — pass through as-is
                    remapped_integrations.append(item)
                else:
                    # Map was fetched but this ID had no match — drop it
                    unmatched_channels.append(item)
            if unmatched_channels and validate:
                alert_name = formatted.get('alertName', 'unknown')
                print(f"  Warning: '{alert_name}' — {len(unmatched_channels)} integrationId(s) not found in target and will be omitted: {unmatched_channels}")
            formatted['integrationIds'] = remapped_integrations

        # Remap ruleIds (custom event specs) to target IDs dynamically
        if 'eventFilteringConfiguration' in formatted and isinstance(formatted['eventFilteringConfiguration'], dict):
            filtering_config = formatted['eventFilteringConfiguration']
            if 'ruleIds' in filtering_config and isinstance(filtering_config['ruleIds'], list):
                remapped_rules = []
                unmatched_rules = []
                for item in filtering_config['ruleIds']:
                    if item in self.event_id_map:
                        remapped_rules.append(self.event_id_map[item])
                    elif not self._event_map_fetched:
                        # Map fetch was never attempted — pass through as-is
                        remapped_rules.append(item)
                    else:
                        # Map was fetched but this ID had no match — drop it
                        unmatched_rules.append(item)
                if unmatched_rules and validate:
                    alert_name = formatted.get('alertName', 'unknown')
                    print(f"  Warning: '{alert_name}' — {len(unmatched_rules)} ruleId(s) not found in target and will be omitted: {unmatched_rules}")
                filtering_config['ruleIds'] = remapped_rules

        # Validate that the event filtering configuration has at least one selector.
        # Only applied when preparing an outbound payload, not during comparison.
        if validate:
            efc = formatted.get('eventFilteringConfiguration', {})
            query = efc.get('query') or ''
            rule_ids = efc.get('ruleIds') or []
            event_types = efc.get('eventTypes') or []
            app_alert_ids = efc.get('applicationAlertConfigIds') or []
            if not query and not rule_ids and not event_types and not app_alert_ids:
                raise ValueError(
                    "eventFilteringConfiguration has no query, ruleIds, eventTypes, or applicationAlertConfigIds — "
                    "at least one must be set"
                )

        return formatted

    def _get_channel_id_map(self) -> Dict[str, str]:
        """Fetch alert channels from source and target to build a source-ID to target-ID map."""
        channel_id_map = {}
        try:
            source_channels = []
            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}/api/events/settings/alertingChannels",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl
                    )
                    if response.status_code == 200:
                        source_channels = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}/api/events/settings/alertingChannels",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                if response.status_code == 200:
                    source_channels = response.json()

            response = requests.get(
                f"{self.config.target_url}/api/events/settings/alertingChannels",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            target_channels = response.json() if response.status_code == 200 else []

            target_by_name = {c.get('name'): c.get('id') for c in target_channels if c.get('name') and c.get('id')}
            for sc in source_channels:
                sc_name = sc.get('name')
                sc_id = sc.get('id')
                if sc_name and sc_id and sc_name in target_by_name:
                    channel_id_map[sc_id] = target_by_name[sc_name]

            self._channel_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build alerting channels ID map: {e}")

        return channel_id_map

    def _get_event_id_map(self) -> Dict[str, str]:
        """Fetch custom events from source and target to build a source-ID to target-ID map."""
        event_id_map = {}
        try:
            source_events = []
            if self.config.events_source == "file":
                if self.config.source_url and self.config.source_token:
                    response = requests.get(
                        f"{self.config.source_url}/api/events/settings/event-specifications/custom",
                        headers=self.config.get_source_headers(),
                        verify=self.config.verify_ssl
                    )
                    if response.status_code == 200:
                        source_events = response.json()
            else:
                response = requests.get(
                    f"{self.config.source_url}/api/events/settings/event-specifications/custom",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                if response.status_code == 200:
                    source_events = response.json()

            response = requests.get(
                f"{self.config.target_url}/api/events/settings/event-specifications/custom",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            target_events = response.json() if response.status_code == 200 else []

            target_by_name = {e.get('name'): e.get('id') for e in target_events if e.get('name') and e.get('id')}
            for se in source_events:
                se_name = se.get('name')
                se_id = se.get('id')
                if se_name and se_id and se_name in target_by_name:
                    event_id_map[se_id] = target_by_name[se_name]

            self._event_map_fetched = True

        except Exception as e:
            print(f"Warning: Failed to build custom events ID map: {e}")

        return event_id_map

    def _configs_are_equal(self, source: Dict[str, Any], target: Dict[str, Any]) -> bool:
        """Return True if source and target represent the same alert config content.

        Normalizes both configurations and compares their content-only fields,
        excluding system-assigned and non-content fields like id and lastUpdated.
        """
        # Normalize both sides without validation — target is already on the server,
        # source validation happens separately at send time.
        try:
            src_norm = self._format_config_for_api(source, validate=False)
            tgt_norm = self._format_config_for_api(target, validate=False)
        except ValueError:
            # alertName missing — can't compare meaningfully
            return False

        # Fields to exclude from comparison.
        # integrationIds and ruleIds are cross-system references that may not match
        # between source and target (different IDs for the same channels/events), so
        # they are excluded to avoid spurious duplicate prompts.
        exclude_fields = {
            'id', 'lastUpdated', 'invalid', 'alertChannelNames', 'applicationNames',
            'integrationIds', 'ruleIds',
        }

        src_content = {k: v for k, v in src_norm.items() if k not in exclude_fields}
        tgt_content = {k: v for k, v in tgt_norm.items() if k not in exclude_fields}

        # Normalise eventFilteringConfiguration: remove ruleIds (cross-system) and
        # sort eventTypes so order differences don't trigger false positives.
        for content in (src_content, tgt_content):
            efc = content.get('eventFilteringConfiguration')
            if isinstance(efc, dict):
                efc = efc.copy()
                efc.pop('ruleIds', None)
                if isinstance(efc.get('eventTypes'), list):
                    efc['eventTypes'] = sorted(efc['eventTypes'])
                content['eventFilteringConfiguration'] = efc

        return src_content == tgt_content
