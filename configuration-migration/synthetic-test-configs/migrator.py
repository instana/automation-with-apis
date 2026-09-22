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


class SyntheticTestConfigMigrator:
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

    def _prompt_for_duplicate_synthetic_test(self, test_label: str) -> str:
        """Prompt user for action when a duplicate synthetic test is found.

        Respects config.on_duplicate when set to 'skip', 'update', or 'cancel'
        so that non-interactive runs (e.g. CI) do not block on stdin.

        Args:
            test_label: Label of the duplicate synthetic test

        Returns:
            User choice: 'skip', 'update', or 'cancel'
        """
        # Honour non-interactive config setting first
        if self.config.on_duplicate in ('skip', 'update', 'cancel'):
            return self.config.on_duplicate

        while True:
            print(f"\nSynthetic test '{test_label}' already exists in the target system.")
            print("Choose an action:")
            print("  [s] Skip")
            print("  [u] Update existing synthetic test")
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

    def _sanitize_payload(self, test_config: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare synthetic test payload for target POST or PUT request.

        Removes read-only backend metadata (ids, timestamps, tenant, derived labels).

        Args:
            test_config: Source synthetic test configuration dict

        Returns:
            Sanitized configuration dict ready for API request
        """
        payload = copy.deepcopy(test_config)

        for field in READ_ONLY_FIELDS:
            payload.pop(field, None)

        # Filter out empty string timeout if present in configuration
        if isinstance(payload.get('configuration'), dict):
            if payload['configuration'].get('timeout') == '':
                payload['configuration'].pop('timeout', None)

        return payload

    def _update_synthetic_test_config(self, test_config: Dict[str, Any], target_id: str) -> bool:
        """Update a synthetic test in the target backend.

        Args:
            test_config: The source synthetic test config
            target_id: The existing target synthetic test ID to update

        Returns:
            True if successful, False otherwise
        """
        label = test_config.get('label', target_id)
        payload = self._sanitize_payload(test_config)
        try:
            response = requests.put(
                f"{self.config.target_url}{self.req_synthetic_test_config}/{target_id}",
                headers=self.config.get_target_headers(),
                json=payload,
                verify=self.config.verify_ssl,
            )
            response.raise_for_status()
            print(f"Updated synthetic test '{label}' (Target ID: {target_id})")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Error updating synthetic test '{label}' (Target ID: {target_id}): {e}")
            return False

    def _create_synthetic_test_config(self, test_config: Dict[str, Any]) -> Optional[str]:
        """Create a synthetic test in the target backend using the full payload.

        Args:
            test_config: The source synthetic test config

        Returns:
            The new target synthetic test ID on success, or None on failure.
        """
        label = test_config.get('label', 'Unnamed test')
        payload = self._sanitize_payload(test_config)
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
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error creating synthetic test '{label}' in target backend: {e}")
            return None

    def _migrate_single_test(
        self,
        source_test: Dict[str, Any],
        synthetic_test_mapping: Dict[str, str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """Process migration for a single synthetic test item.

        Returns:
            Tuple of (status: 'migrated'|'updated'|'skipped'|'cancelled'|None, new_target_id: Optional[str])
        """
        source_id = source_test.get('id')
        source_label = source_test.get('label')

        if not source_label or not source_id:
            print(f"Skipping synthetic test with missing label or id: {source_test}")
            return None, None

        if source_id in synthetic_test_mapping:
            choice = self._prompt_for_duplicate_synthetic_test(str(source_label))
            if choice == 'skip':
                print(f"Synthetic test '{source_label}' already exists in target backend, skipping")
                return 'skipped', None
            elif choice == 'update':
                target_id = synthetic_test_mapping[source_id]
                updated = self._update_synthetic_test_config(source_test, target_id)
                return ('updated', None) if updated else (None, None)
            elif choice == 'cancel':
                print("Migration cancelled by user")
                return 'cancelled', None
            return 'skipped', None

        new_target_id = self._create_synthetic_test_config(source_test)
        if new_target_id is not None:
            return 'migrated', new_target_id
        return None, None

    def migrate(self) -> Dict[str, Any]:
        """Perform the migration of the synthetic test configurations.

        Returns:
            Dictionary with counts and synthetic_test ID mapping
        """
        self.config.validate()
        print("Starting migration of synthetic test configurations...")

        source_synthetic_tests = self._get_source_synthetic_test_config()
        if source_synthetic_tests is None or not source_synthetic_tests:
            count = 0 if source_synthetic_tests is None else len(source_synthetic_tests)
            if not source_synthetic_tests and source_synthetic_tests is not None:
                print("No source synthetic test configurations found.")
            return {"source": count, "migrated": 0, "updated": 0, "skipped": 0, "synthetic_test_mapping": {}}

        target_synthetic_tests = self._get_target_synthetic_test_config()
        if target_synthetic_tests is None:
            return {"source": len(source_synthetic_tests), "migrated": 0, "updated": 0, "skipped": 0, "synthetic_test_mapping": {}}

        synthetic_test_mapping = self._build_synthetic_test_mapping(source_synthetic_tests, target_synthetic_tests)
        migrated_count = 0
        skipped_count = 0
        updated_count = 0

        for source_test in source_synthetic_tests:
            status, new_target_id = self._migrate_single_test(source_test, synthetic_test_mapping)
            if status == 'migrated' and new_target_id:
                synthetic_test_mapping[source_test['id']] = new_target_id
                migrated_count += 1
            elif status == 'updated':
                updated_count += 1
            elif status == 'skipped':
                skipped_count += 1
            elif status == 'cancelled':
                break

        print(f"Migration complete. Found {len(source_synthetic_tests)} source synthetic tests, "
              f"migrated {migrated_count}, updated {updated_count}, "
              f"skipped {skipped_count} existing synthetic tests.")

        return {
            "source": len(source_synthetic_tests),
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "synthetic_test_mapping": synthetic_test_mapping,
        }
