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
            Dictionary with counts of source, migrated, and skipped channels
        """
        # Validate configuration before proceeding
        self.config.validate()
        
        print("Starting migration of alert channel configurations...")
        
        # Get source channels
        source_channels = self._get_source_channels()
        if source_channels is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}
        
        # Get target channels to avoid duplicates
        target_channels = self._get_target_channels()
        if target_channels is None:
            return {"source": len(source_channels), "migrated": 0, "updated": 0, "skipped": 0}
        
        # Extract names of existing channels in target system for comparison
        target_channel_names = [channel.get('name') for channel in target_channels if channel.get('name')]
        
        # Counter for migrated channels
        migrated_count = 0
        skipped_count = 0
        updated_count = 0
        source_channels_count = len(source_channels)
        
        # Process each alert channel from source
        for channel in source_channels:
            # Extract channel name for comparison
            channel_name = channel.get('name')
            
            if not channel_name:
                print("Skipping channel with no name")
                continue
            
            # Check if channel with same name already exists in target
            if channel_name in target_channel_names:
                # Prompt user for choice
                choice = self._prompt_for_duplicate_channel(str(channel_name))
                if choice == 'skip':
                    print(f"Skipping channel '{channel_name}' - already exists in target system")
                    skipped_count += 1
                    continue
                if choice == 'update':
                    print(f"Updating channel '{channel_name}' - already exists in target system")
                    if self._update_channel(channel, str(channel_name), target_channels):
                        updated_count += 1
                        continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break
                
            # Note: We keep the 'id' field as the API seems to require it
            # Create the channel in target system
            if self._create_channel(channel, str(channel_name)):
                migrated_count += 1
        
        print(f"Migration complete. Found {source_channels_count} source channels, "
              f"migrated {migrated_count} alert channels, updated {updated_count} channels, "
              f"skipped {skipped_count} existing channels.")
        
        return {
            "source": source_channels_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count
        }
    
    def _format_channel_for_api(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        """Format channel data according to the specific channel type requirements.
        
        Args:
            channel: The channel data to format
            
        Returns:
            Formatted channel data for API request
        """
        # Create a copy to avoid modifying the original
        formatted = channel.copy()
        
        # Remove fields that shouldn't be sent in creation/update
        # Note: We keep the 'id' field as the API seems to require it
        if 'rbacTags' in formatted:
            del formatted['rbacTags']
            
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
            if 'instanaUrl' not in formatted:
                formatted['instanaUrl'] = "https://instana.example.com"
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
            # Format the channel data for the API
            formatted_channel = self._format_channel_for_api(channel)
            
            # Debug: Print the formatted data being sent
            print(f"Creating channel '{channel_name}' with data:")
            print(json.dumps(formatted_channel, indent=2))
            
            # Debug: Print headers being sent
            headers = self.config.get_target_headers()
            print(f"Request headers: {headers}")
            
            response = requests.post(
                f"{self.config.target_url}{self.req_alert_channels}",
                headers=headers,
                json=formatted_channel,
                verify=self.config.verify_ssl
            )
            
            # Debug: Print response details
            print(f"Response status: {response.status_code}")
            print(f"Response headers: {dict(response.headers)}")
            print(f"Response content: {response.text[:500]}...")
            
            response.raise_for_status()
            new_channel = response.json()
            
            if 'id' in new_channel:
                print(f"Migrated alert channel '{channel_name}' (Target ID: {new_channel['id']})")
                return True
            else:
                print(f"Failed to migrate alert channel '{channel_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to migrate alert channel '{channel_name}'")
            print(f"Error: {e}")
            return False
            
    def _update_channel(self, channel: Dict[str, Any], channel_name: str, target_channels: List[Dict[str, Any]]) -> bool:
        """Update an existing alert channel in the target backend.
        
        Args:
            channel: Alert channel configuration to update
            channel_name: Name of the channel for logging
            target_channels: List of channels from the target system
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the provided target_channels instead of making another API call
            if not target_channels:
                print(f"No target channels provided for updating '{channel_name}'")
                return False
            
            # Find the matching channel in target system by name
            target_channel = next((c for c in target_channels if c.get('name') == channel_name), None)
            if not target_channel or 'id' not in target_channel:
                print(f"Failed to find matching target channel for '{channel_name}'")
                return False
            
            # Use the target channel ID
            target_channel_id = target_channel['id']
            print(f"Updating channel with ID: {target_channel_id}")
            
            # Format the channel data for the API
            formatted_channel = self._format_channel_for_api(channel)
            
            response = requests.put(
                f"{self.config.target_url}{self.req_alert_channels}/{target_channel_id}",
                headers=self.config.get_target_headers(),
                json=formatted_channel,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            updated_channel = response.json()
            
            if 'id' in updated_channel:
                print(f"Updated alert channel '{channel_name}' (Target ID: {updated_channel['id']})")
                return True
            else:
                print(f"Failed to update alert channel '{channel_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to update alert channel '{channel_name}'")
            print(f"Error: {e}")
            return False

# Made with Bob