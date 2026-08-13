"""Core functionality for migrating maintenance configurations between backends."""

import sys
import os
import requests
import urllib3
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config

# Fields the list endpoint returns but the create/update endpoint does not
# accept. They are all computed by the server, so they must be dropped before
# writing or the request is rejected.
SERVER_COMPUTED_FIELDS = (
    'applicationNames',   # derived from the dynamic focus query
    'occurrence',         # next computed start/end
    'invalid',            # server-side validation result
    'lastUpdated',        # server timestamp
    'state',              # UNSCHEDULED / SCHEDULED / ACTIVE / PAUSED / EXPIRED
    # Returned by real backends but absent from the documented write schema, so
    # it is server-maintained. Sending it back risks rejection on a backend
    # that validates unknown fields strictly.
    'validVersion',
)

# States the write endpoint refuses to accept. Determined empirically against a
# real backend: it answers 400 "The maintenance window is already expired." (or
# "... already unscheduled.") for these, which is not documented in the API
# specification. A window in one of these states cannot be recreated elsewhere
# at all, so there is nothing to gain from attempting it.
UNMIGRATABLE_STATES = {
    'EXPIRED': 'already expired',
    'UNSCHEDULED': 'already unscheduled',
}

# Config.events_file_path is shared by every migrator and defaults to this.
# Writing maintenance configs there would clobber the custom events file.
DEFAULT_EVENTS_FILE = "source_events.json"
MAINTENANCE_FILE = "source_maintenance_configs.json"


class MaintenanceConfigsMigrator:
    """Handles migration of maintenance configurations between backends.

    Uses the v2 API. Unlike most resources, the create endpoint takes the
    configuration's ID from the caller, so source IDs are preserved in the
    target. That makes identity exact rather than name-based, and makes
    re-running the migration naturally idempotent.
    """

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details
        """
        self.config = config
        # v1 (/api/settings/maintenance) is deprecated; v2 is the current API.
        self.req_maintenance = "/api/settings/v2/maintenance"

        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, Any]:
        """Perform the migration of maintenance configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, skipped and
            failed configurations
        """
        # Validate configuration before proceeding
        self.config.validate()

        print("Starting migration of maintenance configurations...")

        source_configs = self._get_source_configs()
        if source_configs is None:
            return self._empty_result(0)

        target_configs = self._get_target_configs()
        if target_configs is None:
            print("Could not retrieve target maintenance configurations, aborting migration.")
            return self._empty_result(len(source_configs))

        # Identity is the ID, because the API lets us choose it on create.
        existing_ids = {c['id'] for c in target_configs if c.get('id')}
        print(f"Found {len(existing_ids)} existing maintenance configurations in target")

        migrated_count = 0
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        unmigratable: List[tuple] = []

        for source_config in source_configs:
            config_id = source_config.get('id')
            config_name = source_config.get('name')

            if not config_id or not config_name:
                print(f"Skipping maintenance configuration with missing id or name: {source_config}")
                skipped_count += 1
                continue

            # The backend rejects a window that has already elapsed, so there is
            # no point sending it. Collected and reported together at the end
            # rather than printing a line each, since on a long-lived source
            # most windows are in this state.
            reason = self._unmigratable_reason(source_config)
            if reason:
                unmigratable.append((config_name, reason))
                skipped_count += 1
                continue

            already_exists = config_id in existing_ids

            if already_exists:
                choice = self._prompt_for_duplicate_config(config_name)

                if choice == 'cancel':
                    print("Migration cancelled by user")
                    break

                if choice == 'skip':
                    print(f"Maintenance configuration '{config_name}' already exists in target, skipping")
                    skipped_count += 1
                    continue

            payload = self._prepare_config(source_config)
            if payload is None:
                skipped_count += 1
                continue

            if self._put_config(payload, config_name):
                if already_exists:
                    updated_count += 1
                else:
                    migrated_count += 1
                    existing_ids.add(config_id)
            else:
                failed_count += 1

        print(f"Migration complete. Found {len(source_configs)} source maintenance configurations, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_count}, failed {failed_count}.")

        self._report_unmigratable(unmigratable)

        return {
            "source": len(source_configs),
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }

    def _empty_result(self, source_count: int) -> Dict[str, Any]:
        """Build a zeroed result dict.

        Every early return must carry source/migrated/updated/skipped because
        cli.py reads result["migrated"] and result["updated"].

        Args:
            source_count: Number of source configurations found, if any

        Returns:
            Result dictionary with zero counts
        """
        return {
            "source": source_count,
            "migrated": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
        }

    def _report_unmigratable(self, entries: List[tuple]) -> None:
        """Explain the windows that were skipped because the backend rejects them.

        Args:
            entries: (name, reason) pairs for the skipped configurations
        """
        if not entries:
            return

        by_reason: Dict[str, List[str]] = {}
        for name, reason in entries:
            by_reason.setdefault(reason, []).append(name)

        print(f"\nNote: {len(entries)} maintenance window(s) could not be migrated "
              f"because the target backend rejects them:")
        for reason, names in sorted(by_reason.items()):
            print(f"  {len(names)} {reason}:")
            for name in names[:5]:
                print(f"    - {name}")
            if len(names) > 5:
                print(f"    ... and {len(names) - 5} more")
        print("This is a backend restriction, not a migration failure: a window whose")
        print("schedule has already elapsed cannot be recreated on another system.")

    # ------------------------------------------------------------------
    # Source acquisition
    # ------------------------------------------------------------------

    def _get_source_configs(self) -> Optional[List[Dict[str, Any]]]:
        """Get all maintenance configurations from the source backend or a file.

        Returns:
            List of maintenance configurations or None if failed
        """
        if self.config.events_source.lower() == "file":
            return self._load_source_from_file()
        return self._fetch_source_from_api()

    def _load_source_from_file(self) -> Optional[List[Dict[str, Any]]]:
        """Read maintenance configurations from a local JSON file.

        Returns:
            List of maintenance configurations or None if failed
        """
        file_path = self.config.events_file_path
        try:
            print(f"Reading maintenance configurations from {file_path} file...")
            with open(file_path, 'r') as f:
                raw = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading {file_path} file: {e}")
            print("Make sure the file exists and contains valid JSON")
            return None

        configs = self._normalize_source_payload(raw)
        if configs is None:
            return None

        print(f"Successfully loaded {len(configs)} maintenance configurations from file")
        return configs

    def _normalize_source_payload(self, raw: Any) -> Optional[List[Dict[str, Any]]]:
        """Accept either the export envelope or a bare configuration array.

        Args:
            raw: Parsed JSON from the source file

        Returns:
            List of maintenance configurations or None if the shape is unusable
        """
        if isinstance(raw, list):
            return raw

        if isinstance(raw, dict):
            configs = raw.get('maintenanceConfigs')
            if isinstance(configs, list):
                return configs
            print("Error: file is a JSON object but has no 'maintenanceConfigs' array")
            return None

        print("Error: expected a JSON array of maintenance configurations "
              "or an object with a 'maintenanceConfigs' array")
        return None

    def _fetch_source_from_api(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch maintenance configurations from the source API.

        Returns:
            List of maintenance configurations or None if failed
        """
        print("Fetching maintenance configurations from API endpoint...")
        configs = self._get_configs(
            self.config.source_url,
            self.config.get_source_headers(),
            "source",
        )
        if configs is None:
            return None

        print(f"Successfully fetched {len(configs)} maintenance configurations from API")
        self._write_source_file(configs)
        return configs

    def _get_configs(self, base_url: str, headers: Dict[str, str], label: str) -> Optional[List[Dict[str, Any]]]:
        """Get the maintenance configuration list from a backend.

        Args:
            base_url: Base URL of the backend
            headers: Headers for authentication
            label: 'source' or 'target', for log messages

        Returns:
            List of maintenance configurations or None if failed
        """
        try:
            response = requests.get(
                f"{base_url}{self.req_maintenance}",
                headers=headers,
                verify=self.config.verify_ssl,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
            configs = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving {label} maintenance configurations: {e}")
            self._print_error_body(e)
            return None

        # A misconfigured URL can return a JSON error object where a list is
        # expected. Treat that as a failure rather than as "none configured".
        if not isinstance(configs, list):
            print(f"Error: unexpected response from {label} backend, "
                  f"expected a list of maintenance configurations")
            return None

        return configs

    def _get_target_configs(self) -> Optional[List[Dict[str, Any]]]:
        """Get all maintenance configurations from the target backend.

        Returns:
            List of maintenance configurations or None if failed
        """
        print("Fetching maintenance configurations from target API endpoint...")
        return self._get_configs(
            self.config.target_url,
            self.config.get_target_headers(),
            "target",
        )

    def _resolve_source_file_path(self) -> str:
        """Pick where to persist fetched configurations.

        events_file_path is shared by all migrators and defaults to
        source_events.json, so writing here would destroy the custom events
        source file.

        Returns:
            Path to write the fetched configurations to
        """
        if self.config.events_file_path == DEFAULT_EVENTS_FILE:
            print(f"Note: writing fetched maintenance configurations to {MAINTENANCE_FILE} "
                  f"(use --events-file-path to override)")
            return MAINTENANCE_FILE
        return self.config.events_file_path

    def _write_source_file(self, configs: List[Dict[str, Any]]) -> None:
        """Persist fetched configurations so they can be reused as a file source.

        Args:
            configs: Maintenance configurations to write
        """
        envelope = {
            "version": 1,
            "resource": "maintenance-configs",
            "exportedAt": datetime.now(timezone.utc).isoformat(),
            "sourceUrl": self.config.source_url,
            "maintenanceConfigs": configs,
        }
        file_path = self._resolve_source_file_path()
        try:
            with open(file_path, 'w') as f:
                json.dump(envelope, f, indent=2)
        except OSError as e:
            # A read-only working directory must not abort the migration.
            print(f"Warning: could not write {file_path}: {e}")

    # ------------------------------------------------------------------
    # Transformation
    # ------------------------------------------------------------------

    def _prepare_config(self, source_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Strip server-computed fields and validate the required ones.

        Args:
            source_config: Maintenance configuration as returned by the source

        Returns:
            A payload accepted by the create/update endpoint, or None if the
            record cannot be migrated
        """
        payload = {
            key: value
            for key, value in source_config.items()
            if key not in SERVER_COMPUTED_FIELDS
        }

        # id, name, query and scheduling are required by the API. Catch a
        # missing one here rather than sending a request that must fail.
        #
        # id and name identify the configuration, so they have to be non-empty.
        # query and scheduling only have to be present: an empty query is
        # legitimate and common, meaning the window is not scoped to a subset
        # of entities. Testing it for truthiness would wrongly skip those.
        missing = [f for f in ('id', 'name') if not payload.get(f)]
        missing += [f for f in ('query', 'scheduling') if payload.get(f) is None]
        if missing:
            print(f"Skipping maintenance configuration '{source_config.get('name', 'unknown')}' - "
                  f"missing required field(s): {', '.join(missing)}")
            return None

        scheduling = payload['scheduling']
        if not isinstance(scheduling, dict):
            print(f"Skipping maintenance configuration '{payload['name']}' - "
                  f"scheduling is not an object")
            return None

        # scheduling is polymorphic on type: ONE_TIME carries start and
        # duration, RECURRENT additionally carries rrule and timezoneId.
        sched_missing = [f for f in ('type', 'start', 'duration') if scheduling.get(f) is None]
        if sched_missing:
            print(f"Skipping maintenance configuration '{payload['name']}' - "
                  f"scheduling missing: {', '.join(sched_missing)}")
            return None

        if scheduling.get('type') == 'RECURRENT' and not scheduling.get('rrule'):
            print(f"Skipping maintenance configuration '{payload['name']}' - "
                  f"recurrent schedule has no rrule")
            return None

        return payload

    def _unmigratable_reason(self, source_config: Dict[str, Any]) -> Optional[str]:
        """Report why the backend would refuse this window, if it would.

        The source backend computes the window's state and returns it, which is
        authoritative. A recurrent window can expire too, for example when its
        rrule carries an UNTIL or COUNT that is exhausted, so the state has to be
        read rather than inferred from the start time.

        Falls back to comparing the start time for a hand-written source file
        with no state field. That can only identify an elapsed one-time window,
        so a rejection may still come back from the API; it is reported as a
        failure in that case.

        Args:
            source_config: Maintenance configuration as returned by the source,
                before server-computed fields are stripped

        Returns:
            A short reason if the window cannot be migrated, otherwise None
        """
        state = source_config.get('state')
        if state is not None:
            return UNMIGRATABLE_STATES.get(state)

        # No state to go on, so fall back to the one case that can be inferred.
        scheduling = source_config.get('scheduling') or {}
        if scheduling.get('type') != 'ONE_TIME':
            return None

        start = scheduling.get('start')
        if not isinstance(start, (int, float)):
            return None

        # start is epoch milliseconds.
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        return UNMIGRATABLE_STATES['EXPIRED'] if start < now_ms else None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def _put_config(self, payload: Dict[str, Any], config_name: str) -> bool:
        """Create or update a maintenance configuration in the target backend.

        The endpoint is create-or-update keyed on the ID in the path, so the
        source ID is preserved rather than a new one being generated.

        Args:
            payload: Prepared maintenance configuration
            config_name: Name of the configuration, for log messages

        Returns:
            True if successful, False otherwise
        """
        config_id = payload['id']
        try:
            response = requests.put(
                f"{self.config.target_url}{self.req_maintenance}/{config_id}",
                headers=self.config.get_target_headers(),
                json=payload,
                verify=self.config.verify_ssl,
                timeout=self.config.request_timeout,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error writing maintenance configuration '{config_name}': {e}")
            self._print_error_body(e)
            return False

        print(f"Applied maintenance configuration '{config_name}' (ID: {config_id})")
        return True

    # ------------------------------------------------------------------
    # Duplicate handling
    # ------------------------------------------------------------------

    def _prompt_for_duplicate_config(self, config_name: str) -> str:
        """Decide what to do about a configuration that already exists.

        Args:
            config_name: Name of the duplicate configuration

        Returns:
            'skip', 'update', or 'cancel'
        """
        if self.config.on_duplicate != "ask":
            return self.config.on_duplicate

        if not sys.stdin.isatty():
            print(f"Non-interactive mode: Skipping duplicate maintenance configuration '{config_name}'.")
            return 'skip'

        while True:
            print(f"\nMaintenance configuration '{config_name}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update it with the source version")
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print_error_body(self, error: Exception) -> None:
        """Print an API error response body, which usually explains the failure.

        Args:
            error: The raised request exception
        """
        response = getattr(error, 'response', None)
        if response is None:
            return
        try:
            print(f"API Error Details: {response.json()}")
        except (ValueError, json.JSONDecodeError):
            body = (response.text or '')[:500]
            if body:
                print(f"API Error Details (raw): {body}")
