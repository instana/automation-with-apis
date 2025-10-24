"""Core functionality for migrating custom events between backends."""

import sys
import requests
import urllib3
import json
from typing import Dict, List, Any, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config


class EventsMigrator:
    """Handles migration of custom events between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.
        
        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_custom_events = "/api/events/settings/event-specifications/custom"
        
        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def migrate(self) -> Dict[str, int]:
        """Perform the migration of custom events.
        
        Returns:
            Dictionary with counts of source, migrated, and skipped events
        """
        # Validate configuration before proceeding
        self.config.validate()
        
        print("Starting migration of custom event configurations...")
        
        # Get source events
        source_events = self._get_source_events()
        if source_events is None:
            return {"source": 0, "migrated": 0, "skipped": 0}
        
        # Get target events to avoid duplicates
        target_events = self._get_target_events()
        if target_events is None:
            return {"source": len(source_events), "migrated": 0, "skipped": 0}
        
        #Extract names of existing events in target system for comparison
        target_event_names = [event.get('name') for event in target_events if event.get('name')]
        
        # Counter for migrated events
        migrated_count = 0
        skipped_count = 0
        updated_count = 0
        source_events_count = len(source_events)
        
        # Process each custom event from source
        for event in source_events:
            # Extract event name for comparison
            event_name = event.get('name')
            event_query:Any | None = event.get('query')

            if not event_name:
                print("Skipping event with no name")
                continue

            if event_query and isinstance(event_query, str) and ".id" in event_query:
                skipped_count += 1
                print(f"Skipping event '{event_name}' - query contains id reference from source system")
                continue
            
            # Check if event with same name already exists in target
            if event_name in target_event_names:
                # Prompt user for choice
                choice = self._prompt_for_duplicate_event(str(event_name))
                if choice == 'skip':
                    print(f"Skipping event '{event_name}' - already exists in target system")
                    skipped_count += 1
                    continue
                if choice == 'update':
                    print(f"Updating event '{event_name}' - already exists in target system")
                    if self._update_event(event, str(event_name), target_events):
                        updated_count += 1
                        continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break
                
            if 'id' in event:
                del event['id']
            # Create the event in target system
            if self._create_event(event, str(event_name)):
                migrated_count += 1
        
        print(f"Migration complete. Found {source_events_count} source events, "
              f"migrated {migrated_count} custom events, updated {updated_count} events, "
              f"skipped {skipped_count} existing events.")
        
        return {
            "source": source_events_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count
        }
    
    def _get_source_events(self) -> Optional[List[Dict[str, Any]]]:
        """Get all custom event configurations from source backend or file.
        
        Returns:
            List of custom event configurations or None if failed
        """
        # Check if we should read from file
        if self.config.events_source.lower() == "file":
            try:
                file_path = self.config.events_file_path
                print(f"Reading custom events from {file_path} file...")
                with open(file_path, 'r') as f:
                    events = json.load(f)
                print(f"Successfully loaded {len(events)} events from file")
                return events
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                print("Make sure the file exists and contains valid JSON")
                return None
        else:
            # Default behavior - fetch from API
            try:
                print("Fetching custom events from API endpoint...")
                response = requests.get(
                    f"{self.config.source_url}{self.req_custom_events}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl
                )
                response.raise_for_status()
                events = response.json()
                
                # Write the response to the configured file path
                with open(self.config.events_file_path, 'w') as f:
                    json.dump(events, f, indent=2)
                
                print(f"Successfully fetched {len(events)} events from API")
                return events
            except requests.exceptions.RequestException as e:
                print(f"Error retrieving source events from API: {e}")
                return None
    
    def _get_target_events(self) -> Optional[List[Dict[str, Any]]]:
        """Get all custom event configurations from target backend.
        
        Returns:
            List of custom event configurations or None if failed
        """
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_custom_events}", 
                headers=self.config.get_target_headers(), 
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving target events: {e}")
            return None
    
    def _prompt_for_duplicate_event(self, event_name: str) -> str:
        """Prompt user for action when a duplicate event is found.
        
        Args:
            event_name: Name of the duplicate event
            
        Returns:
            User choice: 'skip', 'migrate', or 'cancel'
        """
        while True:
            print(f"\nEvent '{event_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing event")
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
    
    def _create_event(self, event: Dict[str, Any], event_name: str) -> bool:
        """Create a custom event in the target backend.
        
        Args:
            event: Event configuration to create
            event_name: Name of the event for logging
            
        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_custom_events}",
                headers=self.config.get_target_headers(),
                json=event,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            new_event = response.json()
            
            if 'id' in new_event:
                print(f"Migrated custom event '{event_name}' (Target ID: {new_event['id']})")
                return True
            else:
                print(f"Failed to migrate custom event '{event_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to migrate custom event '{event_name}'")
            print(f"Error: {e}")
            return False
            
    def _update_event(self, event: Dict[str, Any], event_name: str, target_events: List[Dict[str, Any]]) -> bool:
        """Update an existing custom event in the target backend.
        
        Args:
            event: Event configuration to update
            event_name: Name of the event for logging
            target_events: List of events from the target system
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the provided target_events instead of making another API call
            if not target_events:
                print(f"No target events provided for updating '{event_name}'")
                return False
            
            # Find the matching event in target system by name
            target_event = next((e for e in target_events if e.get('name') == event_name), None)
            if not target_event or 'id' not in target_event:
                print(f"Failed to find matching target event for '{event_name}'")
                return False
            
            # Use the target event ID
            target_event_id = target_event['id']
            print(f"Updating event with ID: {target_event_id}")
            
            # Remove source ID if present and use target ID
            if 'id' in event:
                del event['id']
            
            response = requests.put(
                f"{self.config.target_url}{self.req_custom_events}/{target_event_id}",
                headers=self.config.get_target_headers(),
                json=event,
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            updated_event = response.json()
            
            if 'id' in updated_event:
                print(f"Updated custom event '{event_name}' (Target ID: {updated_event['id']})")
                return True
            else:
                print(f"Failed to update custom event '{event_name}' - no ID returned")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Failed to update custom event '{event_name}'")
            print(f"Error: {e}")
            return False

# Made with Bob
