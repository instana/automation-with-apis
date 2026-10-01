"""Synthetic test configurations migrator between Instana backends."""

import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
import requests
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from permissions import check_permissions, dry_run_connectivity_check, DryRunAbortedError
from utils import MigrationResult, build_api, empty_result, make_result, partial_result, print_dry_run_preview, prompt_duplicate

READ_ONLY_FIELDS = {
    'id',
    'tenantId',
    'createdAt',
    'createdBy',
    'modifiedAt',
    'modifiedBy',
    'locationLabels',
    'locationDisplayLabels',
    'applicationLabels',
    'mobileAppLabels',
    'websiteLabels',
}

_REQUIRED_PERMISSIONS = ["canConfigureSyntheticTests"]


class SyntheticConfigMigrator:
    """Handles migration of synthetic test monitoring configurations between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details
        """
        self.config = config
        self.req_synthetic_test_config = "/api/synthetics/settings/tests"

        # Disable SSL warnings if verify_ssl is False
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get_source_synthetic_test_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all synthetic test configurations from source backend or file.

        Returns:
            List of synthetic test configurations or None if failed
        """
        if self.config.events_source.lower() == "file":
            try:
                file_path = self.config.events_file_path
                print(f"Reading synthetic test configurations from {file_path} file...")
                with open(file_path, 'r') as f:
                    synthetic_tests = json.load(f)
                print(f"Successfully loaded {len(synthetic_tests)} synthetic test configs from file")
                return synthetic_tests
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {self.config.events_file_path} file: {e}")
                print("Make sure the file exists and contains valid JSON")
                return None
        else:
            try:
                print("Fetching synthetic test configurations from source API...")
                response = requests.get(
                    f"{self.config.source_url}{self.req_synthetic_test_config}",
                    headers=self.config.get_source_headers(),
                    verify=self.config.verify_ssl,
                )
                response.raise_for_status()
                synthetic_tests = response.json()
                # Write the response to the configured file path as a local backup
                with open(self.config.events_file_path, 'w') as f:
                    json.dump(synthetic_tests, f, indent=2)
                print(f"Successfully fetched {len(synthetic_tests)} synthetic test configs from API")
                return synthetic_tests
            except requests.exceptions.RequestException as e:
                print(f"Error fetching synthetic test configurations from source API: {e}")
                return None

    def _get_target_synthetic_test_config(self) -> Optional[List[Dict[str, Any]]]:
        """Get all synthetic test configurations from target backend.

        Returns:
            List of synthetic test configurations or None if failed
        """
        try:
            response = requests.get(
                f"{self.config.target_url}{self.req_synthetic_test_config}",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching synthetic test configurations from target API: {e}")
            return None

    def _get_target_locations(self) -> Optional[List[Dict[str, Any]]]:
        """Get all synthetic monitoring locations from the target backend.

        Returns:
            List of location dicts or None if the request failed.
        """
        try:
            response = requests.get(
                f"{self.config.target_url}/api/synthetics/settings/locations",
                headers=self.config.get_target_headers(),
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            data = response.json()
            # The endpoint may return a bare list or a wrapped object like
            # {"locations": [...]} or {"items": [...]}.
            if isinstance(data, list):
                return data
            for key in ('locations', 'items', 'data'):
                if isinstance(data.get(key), list):
                    return data[key]
            print(f"Warning: unexpected locations response shape: {type(data)}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Warning: could not fetch target synthetic locations: {e}")
            return None

    def _build_location_mapping(
        self,
        source_tests: List[Dict[str, Any]],
        target_locations: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, str], Optional[str]]:
        """Build a mapping of source location ID → target location ID.

        Matches by display label (case-insensitive). For any source location
        that has no name match in the target, the first available target
        location is used as a fallback.

        Args:
            source_tests: All source synthetic test dicts (used to collect
                          every source location ID + its display label).
            target_locations: Location dicts from the target backend.

        Returns:
            Tuple of (mapping dict, fallback_location_id).
            The fallback is the first available target location ID, used for
            tests whose locations list is empty or unmapped.
        """
        # Build target label → id lookup (case-insensitive)
        target_by_label: Dict[str, str] = {}
        fallback_id: Optional[str] = None
        for loc in target_locations:
            loc_id = loc.get('id') or loc.get('locationId')
            label = (loc.get('displayLabel') or loc.get('label') or '').strip().lower()
            if loc_id:
                if fallback_id is None:
                    fallback_id = loc_id
                if label:
                    target_by_label[label] = loc_id

        # Collect every source location ID and its display label from all tests.
        # locationDisplayLabels is a dict {id: label} but some backends return a
        # list of strings (the labels only) — in that case we cannot match by name
        # and will rely on the fallback for every location.
        source_id_to_label: Dict[str, str] = {}
        for test in source_tests:
            display_labels = test.get('locationDisplayLabels')
            if isinstance(display_labels, dict):
                for loc_id, display_label in display_labels.items():
                    if loc_id not in source_id_to_label:
                        source_id_to_label[loc_id] = display_label
            # Also collect bare location IDs from the 'locations' list so that
            # tests whose locationDisplayLabels is missing/empty still get a
            # fallback location assigned.
            for loc_id in (test.get('locations') or []):
                if loc_id not in source_id_to_label:
                    source_id_to_label[loc_id] = ''

        mapping: Dict[str, str] = {}
        for src_id, display_label in source_id_to_label.items():
            key = display_label.strip().lower()
            target_id = target_by_label.get(key) or fallback_id
            if target_id:
                mapping[src_id] = target_id

        fallback_count = sum(1 for src_id, tgt_id in mapping.items()
                             if tgt_id == fallback_id
                             and target_by_label.get(source_id_to_label.get(src_id, '').strip().lower()) is None)
        print(f"  Location mapping: {len(source_id_to_label)} source location(s), "
              f"{len(mapping)} mapped "
              f"({fallback_count} using fallback '{fallback_id}')")

        return mapping, fallback_id

    def _build_synthetic_test_mapping(self, source_synthetic_tests: List[Dict], target_synthetic_tests: List[Dict]) -> Dict[str, str]:
        """Build mapping of source synthetic test ID to target synthetic test ID based on label matching."""
        mapping = {}
        target_by_label = {test.get('label'): test.get('id') for test in target_synthetic_tests if test.get('label')}

        for source_test in source_synthetic_tests:
            source_label = source_test.get('label')
            source_id = source_test.get('id')

            if source_label and source_id and source_label in target_by_label:
                target_id = target_by_label[source_label]
                if target_id:
                    mapping[source_id] = target_id

        return mapping

    def _sanitize_payload(
        self,
        test_config: Dict[str, Any],
        location_mapping: Optional[Dict[str, str]] = None,
        fallback_location_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare synthetic test payload for target POST or PUT request.

        Removes read-only backend metadata, cross-backend ID references, and
        remaps location IDs to their target equivalents.

        Args:
            test_config: Source synthetic test configuration dict
            location_mapping: Optional dict of {source_location_id: target_location_id}.
                If provided, the ``locations`` list is remapped.
            fallback_location_id: Target location ID to use when the remapped
                ``locations`` list is empty (covers tests that had no location
                assigned on the source).

        Returns:
            Sanitized configuration dict ready for API request
        """
        payload = copy.deepcopy(test_config)

        for field in READ_ONLY_FIELDS:
            payload.pop(field, None)

        # Strip cross-backend application / website / mobileApp references.
        # These IDs are backend-specific and will not exist on the target.
        for field in ('applicationId', 'applicationLabel', 'applications',
                      'websites', 'mobileApps', 'websiteId', 'mobileAppId'):
            payload.pop(field, None)

        # Remap location IDs when a mapping is available
        if location_mapping is not None:
            source_locations = payload.get('locations') or []
            remapped = [location_mapping[loc_id] for loc_id in source_locations
                        if loc_id in location_mapping]
            # Deduplicate while preserving order
            seen: set = set()
            payload['locations'] = [x for x in remapped if not (x in seen or seen.add(x))]

        # If locations is still empty, inject the fallback so the API doesn't
        # reject the test with "No location provided."
        if not payload.get('locations') and fallback_location_id:
            payload['locations'] = [fallback_location_id]

        # Strip empty-string entries from customProperties — the API rejects
        # maps that contain blank keys or values.
        if isinstance(payload.get('customProperties'), dict):
            payload['customProperties'] = {
                k: v for k, v in payload['customProperties'].items()
                if k and v
            }

        # Filter out empty string timeout if present in configuration
        if isinstance(payload.get('configuration'), dict):
            if payload['configuration'].get('timeout') == '':
                payload['configuration'].pop('timeout', None)

        return payload

    def _update_synthetic_test_config(
        self,
        test_config: Dict[str, Any],
        target_id: str,
        location_mapping: Optional[Dict[str, str]] = None,
        fallback_location_id: Optional[str] = None,
    ) -> bool:
        """Update a synthetic test in the target backend.

        Args:
            test_config: The source synthetic test config
            target_id: The existing target synthetic test ID to update
            location_mapping: Optional source→target location ID mapping.
            fallback_location_id: Target location ID to use when locations is empty.

        Returns:
            True if successful, False otherwise
        """
        label = test_config.get('label', target_id)
        payload = self._sanitize_payload(test_config, location_mapping, fallback_location_id)
        try:
            response = requests.put(
                f"{self.config.target_url}{self.req_synthetic_test_config}/{target_id}",
                headers=self.config.get_target_headers(),
                json=payload,
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            print(f"Updated synthetic test '{label}' (Target ID: {target_id})")
            return 'updated'
        except requests.exceptions.HTTPError as e:
            if 'Synthetics Keystore not configured' in e.response.text:
                print(f"⊘ Skipping synthetic test '{label}': uses credentials not available on target (Keystore not configured)")
                return 'skipped_keystore'
            print(f"Error updating synthetic test '{label}' (Target ID: {target_id}): {e} — {e.response.text}")
            return 'failed'
        except requests.exceptions.RequestException as e:
            print(f"Error updating synthetic test '{label}' (Target ID: {target_id}): {e}")
            return 'failed'

    def _create_synthetic_test_config(
        self,
        test_config: Dict[str, Any],
        location_mapping: Optional[Dict[str, str]] = None,
        fallback_location_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a synthetic test in the target backend using the full payload.

        Args:
            test_config: The source synthetic test config
            location_mapping: Optional source→target location ID mapping.
            fallback_location_id: Target location ID to use when locations is empty.

        Returns:
            The new target synthetic test ID on success, or None on failure.
        """
        label = test_config.get('label', 'Unnamed test')
        payload = self._sanitize_payload(test_config, location_mapping, fallback_location_id)
        try:
            response = requests.post(
                f"{self.config.target_url}{self.req_synthetic_test_config}",
                headers=self.config.get_target_headers(),
                json=payload,
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            created = response.json()
            target_id = created.get('id') if isinstance(created, dict) else None
            if target_id:
                print(f"Successfully created synthetic test '{label}' (Target ID: {target_id})")
                return target_id
            print(f"Successfully created synthetic test '{label}' (no ID in response)")
            return target_id  # None — caller treats as failed
        except requests.exceptions.HTTPError as e:
            if 'Synthetics Keystore not configured' in e.response.text:
                print(f"⊘ Skipping synthetic test '{label}': uses credentials not available on target (Keystore not configured)")
                return 'skipped_keystore'
            print(f"Error creating synthetic test '{label}' in target backend: {e} — {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error creating synthetic test '{label}' in target backend: {e}")
            return None

    def _migrate_single_test(
        self,
        source_test: Dict[str, Any],
        synthetic_test_mapping: Dict[str, str],
        location_mapping: Optional[Dict[str, str]] = None,
        fallback_location_id: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Process migration for a single synthetic test item.

        Returns:
            Tuple of (status: 'migrated'|'updated'|'skipped'|'cancelled'|'failed', new_target_id: Optional[str])
        """
        source_id = source_test.get('id')
        source_label = source_test.get('label')

        if not source_label or not source_id:
            print(f"Skipping synthetic test with missing label or id: {source_test}")
            return 'skipped', None

        if source_id in synthetic_test_mapping:
            choice = prompt_duplicate("Synthetic test", str(source_label))
            if choice == 'skip':
                print(f"Synthetic test '{source_label}' already exists in target backend, skipping")
                return 'skipped', None
            elif choice == 'update':
                target_id = synthetic_test_mapping[source_id]
                result = self._update_synthetic_test_config(source_test, target_id, location_mapping, fallback_location_id)
                if result == 'updated':
                    return 'updated', None
                elif result == 'skipped_keystore':
                    return 'skipped', None
                return 'failed', None
            elif choice == 'cancel':
                print("Migration cancelled by user")
                return 'cancelled', None
            return 'skipped', None

        result = self._create_synthetic_test_config(source_test, location_mapping, fallback_location_id)
        if result == 'skipped_keystore':
            return 'skipped', None
        if result is not None:
            return 'migrated', result
        return 'failed', None

    def _dry_run(self) -> MigrationResult:
        """Preview what would happen during migration without making any changes.

        Returns:
            Dictionary with would-be counts using the same keys as migrate().
        """
        try:
            source_tests, target_tests = dry_run_connectivity_check(
                self.config,
                fetch_source=self._get_source_synthetic_test_config,
                fetch_target=self._get_target_synthetic_test_config,
                entity_name="synthetic test configs",
                required_permissions=_REQUIRED_PERMISSIONS,
            )
        except DryRunAbortedError:
            return empty_result()

        target_labels = {test.get('label') for test in target_tests if test.get('label')}

        would_create = 0
        would_update = 0
        skipped_invalid = 0
        create_lines: list = []
        update_lines: list = []
        skip_lines: list = []

        for test in source_tests:
            label = test.get('label')
            if not label:
                skip_lines.append("  ✗ Would skip    (synthetic test with missing label)")
                skipped_invalid += 1
                continue
            if label in target_labels:
                update_lines.append(f"  ~ Would update  '{label}' (exists in target)")
                would_update += 1
            else:
                create_lines.append(f"  ✓ Would create  '{label}'")
                would_create += 1

        skipped_total = skipped_invalid
        print_dry_run_preview(
            create_lines, update_lines, skip_lines,
            source_count=len(source_tests),
            target_count=len(target_tests),
            would_create=would_create,
            would_update=would_update,
            skipped_total=skipped_total,
            skipped_detail=f"{skipped_invalid} invalid",
            entity_name="synthetic test configs",
        )
        return make_result(
            source=len(source_tests),
            migrated=would_create,
            updated=would_update,
            skipped=skipped_total,
            skipped_invalid=skipped_total,
        )

    def migrate(self) -> MigrationResult:
        """Perform the migration of the synthetic test configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, skipped, and failed configs.
        """
        self.config.validate()

        if self.config.dry_run:
            return self._dry_run()

        if not check_permissions(self.config, _REQUIRED_PERMISSIONS):
            return empty_result()

        print("Starting migration of synthetic test configurations...")

        source_synthetic_tests = self._get_source_synthetic_test_config()
        if source_synthetic_tests is None:
            return empty_result()
        if not source_synthetic_tests:
            print("No source synthetic test configurations found.")
            return make_result(source=0, migrated=0, updated=0, skipped=0)

        target_synthetic_tests = self._get_target_synthetic_test_config()
        if target_synthetic_tests is None:
            return partial_result(len(source_synthetic_tests))

        # Build location mapping: source location IDs → target location IDs
        target_locations = self._get_target_locations()
        location_mapping: Optional[Dict[str, str]] = None
        fallback_location_id: Optional[str] = None
        if target_locations:
            location_mapping, fallback_location_id = self._build_location_mapping(source_synthetic_tests, target_locations)
        else:
            print("Warning: could not fetch target locations — location IDs will not be remapped.")

        synthetic_test_mapping = self._build_synthetic_test_mapping(source_synthetic_tests, target_synthetic_tests)
        migrated_count = 0
        skipped_count = 0
        updated_count = 0
        failed_count = 0

        for source_test in source_synthetic_tests:
            status, new_target_id = self._migrate_single_test(source_test, synthetic_test_mapping, location_mapping, fallback_location_id)
            if status == 'migrated' and new_target_id:
                synthetic_test_mapping[source_test['id']] = new_target_id
                migrated_count += 1
            elif status == 'updated':
                updated_count += 1
            elif status == 'skipped':
                skipped_count += 1
            elif status == 'failed':
                failed_count += 1
            elif status == 'cancelled':
                break

        print(f"Migration complete. Found {len(source_synthetic_tests)} source synthetic tests, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_count}, failed {failed_count}.")

        return make_result(
            source=len(source_synthetic_tests),
            migrated=migrated_count,
            updated=updated_count,
            skipped=skipped_count,
            failed=failed_count,
        )
