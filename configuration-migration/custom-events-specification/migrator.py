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
            Dictionary with counts of source, migrated, updated, skipped, and failed events
        """
        # Validate configuration before proceeding
        self.config.validate()

        print("Starting migration of custom event configurations...")

        # Get source events
        source_events = self._get_source_events()
        if source_events is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}

        # Get target events to avoid duplicates
        target_events = self._get_target_events()
        if target_events is None:
            return {"source": len(source_events), "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}

        # Build a name → event map for the target so we can compare content
        target_event_map = {e['name']: e for e in target_events if e.get('name')}
        print(f"Found {len(target_events)} existing events in target")

        # Counters
        migrated_count = 0
        skipped_identical = 0
        skipped_unsafe = 0
        skipped_user = 0
        updated_count = 0
        failed_count = 0
        source_events_count = len(source_events)

        # Process each custom event from source
        for event in source_events:
            event_name = event.get('name')
            event_query: Any | None = event.get('query')

            if not event_name:
                print("Skipping event with no name")
                continue

            if event_query and isinstance(event_query, str) and ".id" in event_query:
                skipped_unsafe += 1
                print(f"Skipping event '{event_name}' - query contains id reference from source system")
                continue

            # Check if event with same name already exists in target
            if event_name in target_event_map:
                target_event = target_event_map[event_name]
                if self._events_are_equal(event, target_event):
                    print(f"Skipping event '{event_name}' - identical in target")
                    skipped_identical += 1
                    continue
                choice = self._prompt_for_duplicate_event(str(event_name))
                if choice == 'skip':
                    print(f"Skipping event '{event_name}' - already exists in target system")
                    skipped_user += 1
                    continue
                if choice == 'update':
                    print(f"Updating event '{event_name}' - already exists in target system")
                    if self._update_event(event, str(event_name), target_events):
                        updated_count += 1
                    else:
                        failed_count += 1
                    continue
                elif choice == 'cancel':
                    print("Migration cancelled by user")
                    break

            if 'id' in event:
                del event['id']
            if self._create_event(event, str(event_name)):
                migrated_count += 1
            else:
                failed_count += 1

        skipped_total = skipped_identical + skipped_unsafe + skipped_user
        print(f"Migration complete. Found {source_events_count} source events, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_total} ({skipped_identical} identical, "
              f"{skipped_unsafe} unsafe query, {skipped_user} user skipped), "
              f"failed {failed_count}.")

        return {
            "source": source_events_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped_identical": skipped_identical,
            "skipped_unsafe": skipped_unsafe,
            "skipped_user": skipped_user,
            "failed": failed_count,
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
    
    # Fields present in the target GET response that are assigned by the target
    # system and must be excluded when comparing source vs target content.
    _TARGET_ONLY_FIELDS = frozenset({
        'id', 'lastUpdated', 'validVersion', 'deleted',
        'migrated', 'applicationAlertConfigId', 'infraAlertConfigId',
    })

    def _events_are_equal(self, source: Dict[str, Any], target: Dict[str, Any]) -> bool:
        """Return True if source and target represent the same event content.

        Strips target-system-only fields (id, lastUpdated, etc.) from the
        target before comparing, since those are never present in the source.

        Args:
            source: Event dict from the source system
            target: Event dict from the target system (includes server fields)

        Returns:
            True if all content fields are identical
        """
        target_content = {k: v for k, v in target.items() if k not in self._TARGET_ONLY_FIELDS}
        source_content = {k: v for k, v in source.items() if k not in self._TARGET_ONLY_FIELDS}
        return source_content == target_content

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

        After creation, if the source event was disabled, the target event is
        also disabled via the dedicated /disable sub-endpoint, since the API
        ignores the `enabled` field in the POST body.

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

            if 'id' not in new_event:
                print(f"Failed to migrate custom event '{event_name}' - no ID returned")
                return False

            print(f"Migrated custom event '{event_name}' (Target ID: {new_event['id']})")

            # Disable in target if source event was explicitly disabled
            if event.get('enabled') is False:
                self._disable_event(new_event['id'], event_name)

            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to migrate custom event '{event_name}'")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"API response: {e.response.text}")
            return False

    def _update_event(self, event: Dict[str, Any], event_name: str, target_events: List[Dict[str, Any]]) -> bool:
        """Update an existing custom event in the target backend.

        After updating, if the source event was disabled, the target event is
        also disabled via the dedicated /disable sub-endpoint.

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

            if 'id' not in updated_event:
                print(f"Failed to update custom event '{event_name}' - no ID returned")
                return False

            print(f"Updated custom event '{event_name}' (Target ID: {updated_event['id']})")

            # Disable in target if source event was explicitly disabled
            if event.get('enabled') is False:
                self._disable_event(updated_event['id'], event_name)

            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to update custom event '{event_name}'")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"API response: {e.response.text}")
            return False

    def _disable_event(self, event_id: str, event_name: str) -> None:
        """Disable a custom event in the target backend.

        Called after create/update when the source event has enabled=False,
        because the API ignores the `enabled` field in POST/PUT bodies.

        Args:
            event_id: Target system ID of the event to disable
            event_name: Name of the event for logging
        """
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_custom_events}/{event_id}/disable",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl
            )
            response.raise_for_status()
            print(f"Disabled custom event '{event_name}' (Target ID: {event_id})")
        except requests.exceptions.RequestException as e:
            print(f"Warning: Failed to disable custom event '{event_name}' (Target ID: {event_id})")
            print(f"Error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"API response: {e.response.text}")

# Made with Bob
