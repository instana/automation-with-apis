"""Core functionality for migrating alert channels between backends."""

import sys
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config


class AlertChannelsMigrator:
    """Handles migration of alert channels between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.
        
        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_alert_channels = "/api/events/settings/alertingChannels"
        
        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def migrate(self) -> Dict[str, int]:
        """Perform the migration of alert channels.
        
        Returns:
            Dictionary with counts of source, migrated, updated, skipped_identical,
            skipped_user, and failed channels
        """
        # Validate configuration before proceeding
        self.config.validate()
        
        print("Starting migration of alert channel configurations...")
        
        # Get source channels
        source_channels = self._get_source_channels()
        if source_channels is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}
        
        # Get target channels to avoid duplicates
        target_channels = self._get_target_channels()
        if target_channels is None:
            return {"source": len(source_channels), "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}
        
        print(f"Found {len(target_channels)} existing channels in target")

        # Build lookup maps for the target system.
        # id_map gives an exact match when source and target share the same id
        # (e.g. a channel that was already migrated previously).
        # name_map is the fallback for channels that only share a name.
        target_id_map: Dict[str, Dict[str, Any]] = {
            c['id']: c for c in target_channels if c.get('id')
        }
        target_name_map: Dict[str, Dict[str, Any]] = {
            c['name']: c for c in target_channels if c.get('name')
        }

        # Counters
        migrated_count = 0
        updated_count = 0
        skipped_identical_count = 0
        skipped_unsafe_count = 0
        skipped_user_count = 0
        failed_count = 0
        source_channels_count = len(source_channels)
        
        # Process each alert channel from source
        for channel in source_channels:
            channel_name = channel.get('name')
            source_id = channel.get('id')

            if not channel_name:
                print("Skipping channel with no name")
                continue

            # Resolve the matching target channel.
            # Prefer an exact id match (same channel, already migrated) over a
            # name-only match (duplicate name, potentially different channel).
            target_channel = target_id_map.get(source_id) or target_name_map.get(channel_name)

            if target_channel is not None:
                # Content-based deduplication: skip silently when channels are identical
                if self._channels_are_identical(channel, target_channel):
                    skipped_identical_count += 1
                    continue

                # Content differs — ask the user what to do
                choice = self._prompt_for_duplicate_channel(str(channel_name))
                if choice == 'skip':
                    print(f"Skipping channel '{channel_name}' - already exists in target system")
                    skipped_user_count += 1
                    continue
                elif choice == 'update':
                    print(f"Updating channel '{channel_name}' - already exists in target system")
                    if self._update_channel(channel, str(channel_name), target_channel):
                        updated_count += 1
                    else:
                        failed_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break
                
            # Create the channel in the target system
            if self._create_channel(channel, str(channel_name)):
                migrated_count += 1
            else:
                failed_count += 1
        
        skipped_total = skipped_identical_count + skipped_unsafe_count + skipped_user_count
        print(
            f"Migration complete. Found {source_channels_count} source channels, "
            f"migrated {migrated_count}, updated {updated_count}, "
            f"skipped {skipped_total} "
            f"({skipped_identical_count} identical, "
            f"{skipped_unsafe_count} unsafe, "
            f"{skipped_user_count} user skipped), "
            f"failed {failed_count}."
        )

        return {
            "source": source_channels_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped_identical": skipped_identical_count,
            "skipped_unsafe": skipped_unsafe_count,
            "skipped_user": skipped_user_count,
            "failed": failed_count,
        }
    
    def _channels_are_identical(
        self, source: Dict[str, Any], target: Dict[str, Any]
    ) -> bool:
        """Return True when source and target channels have identical content.

        Fields excluded from comparison:
        - 'id'         — always differs between systems by design
        - 'rbacTags'   — always stripped before sending to the API
        - 'instanaUrl' — always overwritten with the target system URL during formatting
        - 'apiTokenId' — backend-local API token reference; always differs between systems

        Args:
            source: Channel from the source system
            target: Channel from the target system

        Returns:
            True if all meaningful fields are equal, False otherwise
        """
        ignore = {'id', 'rbacTags', 'instanaUrl', 'apiTokenId'}
        source_cmp = {k: v for k, v in source.items() if k not in ignore}
        target_cmp = {k: v for k, v in target.items() if k not in ignore}
        return source_cmp == target_cmp

    def _format_channel_for_api(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        """Format channel data according to the specific channel type requirements.
        
        Args:
            channel: The channel data to format
            
        Returns:
            Formatted channel data for API request
        """
        # Create a copy to avoid modifying the original
        formatted = channel.copy()
        
        # Remove fields that must not be sent to the target API.
        # Note: 'id', 'kind', and 'name' are mandatory in the POST/PUT body per the API spec.
        formatted.pop('rbacTags', None)
            
        # Get the channel type
        channel_type = formatted.get('kind')
        
        # Format according to channel type
        if channel_type == 'EMAIL':
            # Ensure required fields are present
            if 'emails' not in formatted:
                formatted['emails'] = ["example@example.com"]
            if 'customEmailSubjectPrefix' not in formatted:
                formatted['customEmailSubjectPrefix'] = None
                
        elif channel_type == 'SLACK':
            # Ensure required fields are present
            if 'webhookUrl' not in formatted:
                formatted['webhookUrl'] = "https://example.com/webhook"
            if 'channel' not in formatted:
                formatted['channel'] = "alerts"
            if 'emojiRendering' not in formatted:
                formatted['emojiRendering'] = False
                
        elif channel_type == 'WEB_HOOK':
            # Ensure required fields are present
            if 'webhookUrls' not in formatted:
                formatted['webhookUrls'] = ["https://webhook.example.com"]
            if 'headers' not in formatted:
                formatted['headers'] = []
                
        elif channel_type == 'BIDIRECTIONAL_SLACK':
            # Ensure required fields are present
            if 'appId' not in formatted:
                formatted['appId'] = "placeholder_app_id"
            if 'teamId' not in formatted:
                formatted['teamId'] = "placeholder_team_id"
            if 'channelId' not in formatted:
                formatted['channelId'] = "placeholder_channel_id"
            if 'channelName' not in formatted:
                formatted['channelName'] = "alerts"
            if 'emojiRendering' not in formatted:
                formatted['emojiRendering'] = False
                
        elif channel_type == 'BIDIRECTIONAL_MS_TEAMS':
            # Ensure required fields are present
            if 'apiTokenId' not in formatted:
                formatted['apiTokenId'] = "placeholder_token_id"
            if 'channelId' not in formatted:
                formatted['channelId'] = "placeholder_channel_id"
            if 'channelName' not in formatted:
                formatted['channelName'] = "alerts"
            # instanaUrl must point to the target system, not the source
            formatted['instanaUrl'] = self.config.target_url
            if 'serviceUrl' not in formatted:
                formatted['serviceUrl'] = "https://teams.example.com"
            if 'teamId' not in formatted:
                formatted['teamId'] = "placeholder_team_id"
            if 'teamName' not in formatted:
                formatted['teamName'] = "placeholder_team"
            if 'tenantId' not in formatted:
                formatted['tenantId'] = "placeholder_tenant_id"
            if 'tenantName' not in formatted:
                formatted['tenantName'] = "placeholder_tenant"
                
        elif channel_type == 'GOOGLE_CHAT':
            # Ensure required fields are present
            if 'webhookUrl' not in formatted:
                formatted['webhookUrl'] = "https://chat.googleapis.com/webhook"
                
        elif channel_type == 'OFFICE_365':
            # Ensure required fields are present
            if 'webhookUrl' not in formatted:
                formatted['webhookUrl'] = "https://webhook.office365.com/webhook"
                
        elif channel_type == 'OPS_GENIE':
            # Ensure required fields are present
            if 'apiKey' not in formatted:
                formatted['apiKey'] = "placeholder_api_key"
            if 'region' not in formatted:
                formatted['region'] = "US"
            if 'alias' not in formatted:
                formatted['alias'] = ""
            if 'tags' not in formatted:
                formatted['tags'] = ""
                
        elif channel_type == 'PAGER_DUTY':
            # Ensure required fields are present
            if 'serviceIntegrationKey' not in formatted:
                formatted['serviceIntegrationKey'] = "placeholder_integration_key"

        elif channel_type == 'SERVICE_NOW_APPLICATION':
            # instanaUrl must point to the target system, not the source
            formatted['instanaUrl'] = self.config.target_url

        # For any other channel types, keep as is
        # Add more channel types as needed
        
        return formatted
    
    def _get_source_channels(self) -> Optional[List[Dict[str, Any]]]:
        """Get all alert channel configurations from source backend or file.
        
        Returns:
            List of alert channel configurations or None if failed
        """
        # Check if we should read from file
        if self.config.events_source.lower() == "file":
            try:
                file_path = self.config.events_file_path
                print(f"Reading alert channels from {file_path} file...")
                with open(file_path, 'r') as f:
                    channels = json.load(f)
                print(f"Successfully loaded {len(channels)} channels from file")
                return channels
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                print("Make sure the file exists and contains valid JSON")
                return None
        else:
            # Default behavior - fetch from API
            try:
                print("Fetching alert channels from API endpoint...")
                response = requests.get(
                    f"{self.config.source_url}{self.req_alert_channels}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                response.raise_for_status()
                channels = response.json()
                
                # Write the response to the configured file path
                with open(self.config.events_file_path, 'w') as f:
                    json.dump(channels, f, indent=2)
                
                print(f"Successfully fetched {len(channels)} channels from API")
                return channels
            except requests.exceptions.RequestException as e:
                print(f"Error retrieving source channels from API: {e}")
                return None
    
    def _get_target_channels(self) -> Optional[List[Dict[str, Any]]]:
        """Get all alert channel configurations from target backend.
        
        Returns:
            List of alert channel configurations or None if failed
        """
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_alert_channels}", 
                headers=self.config.get_target_headers(), 
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving target channels: {e}")
            return None
    
    def _prompt_for_duplicate_channel(self, channel_name: str) -> str:
        """Prompt user for action when a duplicate channel is found.
        
        Args:
            channel_name: Name of the duplicate channel
            
        Returns:
            User choice: 'skip', 'update', or 'cancel'
        """
        while True:
            print(f"\nAlert channel '{channel_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing channel")
            print("  [c] Cancel migration")
            
            choice = input("Enter your choice [s/u/c]: ").lower()
            
            if choice in ['s', 'skip']:
                return 'skip'
            elif choice in ['u', 'update']:
                return 'update'
            elif choice in ['c', 'cancel']:
                return 'cancel'
            else:
                print("Invalid choice. Please try again.")
    
    def _create_channel(self, channel: Dict[str, Any], channel_name: str) -> bool:
        """Create an alert channel in the target backend.
        
        Args:
            channel: Alert channel configuration to create
            channel_name: Name of the channel for logging
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Format the channel data for the API (strips source id and rbacTags)
            formatted_channel = self._format_channel_for_api(channel)
            
            response = requests.post(
                f"{self.config.target_url}{self.req_alert_channels}",
                headers=self.config.get_target_headers(),
                json=formatted_channel,
                verify=self.config.verify_ssl
            )
            
            if not response.ok:
                print(f"Failed to migrate alert channel '{channel_name}': "
                      f"HTTP {response.status_code} - {response.text}")
                return False

            new_channel = response.json()
            
            if 'id' in new_channel:
                print(f"Migrated alert channel '{channel_name}' (Target ID: {new_channel['id']})")
                return True
            else:
                print(f"Failed to migrate alert channel '{channel_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            error_body = e.response.text if e.response is not None else ""
            print(f"Failed to migrate alert channel '{channel_name}': {e}{f' - {error_body}' if error_body else ''}")
            return False
            
    def _update_channel(self, channel: Dict[str, Any], channel_name: str, target_channel: Dict[str, Any]) -> bool:
        """Update an existing alert channel in the target backend.
        
        Args:
            channel: Alert channel configuration to update
            channel_name: Name of the channel for logging
            target_channel: The already-resolved matching channel in the target system
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if 'id' not in target_channel:
                print(f"Failed to find matching target channel for '{channel_name}'")
                return False

            # Use the target channel ID
            target_channel_id = target_channel['id']
            print(f"Updating channel with ID: {target_channel_id}")
            
            # Format the channel data for the API (strips rbacTags).
            # Replace the source id with the target id — the API requires id in the
            # PUT body and it must match the id in the URL.
            formatted_channel = self._format_channel_for_api(channel)
            formatted_channel['id'] = target_channel_id
            
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_channels}/{target_channel_id}",
                headers=self.config.get_target_headers(),
                json=formatted_channel,
                verify=self.config.verify_ssl
            )

            if not response.ok:
                print(f"Failed to update alert channel '{channel_name}': "
                      f"HTTP {response.status_code} - {response.text}")
                return False

            updated_channel = response.json()
            
            if 'id' in updated_channel:
                print(f"Updated alert channel '{channel_name}' (Target ID: {updated_channel['id']})")
                return True
            else:
                print(f"Failed to update alert channel '{channel_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            error_body = e.response.text if e.response is not None else ""
            print(f"Failed to update alert channel '{channel_name}': {e}{f' - {error_body}' if error_body else ''}")
            return False

# Made with Bob
