"""Core functionality for migrating application configurations between backends.

Migrates Application Perspectives (application configs) using the instana_client SDK.
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config

from typing import Dict, List, Optional

import instana_client
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.models.application_config import ApplicationConfig
from instana_client.models.new_application_config import NewApplicationConfig


def _build_api(url: str, token: str, verify_ssl: bool) -> ApplicationSettingsApi:
    """Create a configured ApplicationSettingsApi client.

    Args:
        url: Base URL of the Instana backend.
        token: API token for authentication.
        verify_ssl: Whether to verify SSL certificates.

    Returns:
        Configured ApplicationSettingsApi instance.
    """
    configuration = instana_client.Configuration(
        host=url,
        api_key={"ApiKeyAuth": token},
        api_key_prefix={"ApiKeyAuth": "apiToken"},
    )
    configuration.verify_ssl = verify_ssl
    api_client = instana_client.ApiClient(configuration)
    return ApplicationSettingsApi(api_client)


class ApplicationConfigMigrator:
    """Handles migration of application configurations (Application Perspectives) between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details.
        """
        self.config = config

    def migrate(self) -> Dict[str, int]:
        """Perform the migration of application configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, and skipped configs.
        """
        self.config.validate()

        print("Starting migration of application configurations...")

        source_api = _build_api(
            self.config.source_url, self.config.source_token, self.config.verify_ssl
        )
        target_api = _build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )

        source_configs = self._get_configs(source_api, "source")
        if source_configs is None:
            return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}

        target_configs = self._get_configs(target_api, "target")
        if target_configs is None:
            return {"source": len(source_configs), "migrated": 0, "updated": 0, "skipped": 0}

        target_labels = {cfg.label for cfg in target_configs}

        migrated_count = 0
        updated_count = 0
        skipped_count = 0
        source_count = len(source_configs)

        for cfg in source_configs:
            label = cfg.label

            if label in target_labels:
                if self.config.on_duplicate == "update":
                    print(f"⟳ Application config '{label}' already exists, updating...")
                    if self._update_config(target_api, cfg, target_configs):
                        updated_count += 1
                    else:
                        skipped_count += 1
                elif self.config.on_duplicate == "skip":
                    print(f"⊘ Application config '{label}' already exists, skipping...")
                    skipped_count += 1
                else:
                    choice = self._prompt_duplicate(label)
                    if choice == "skip":
                        skipped_count += 1
                    elif choice == "update":
                        if self._update_config(target_api, cfg, target_configs):
                            updated_count += 1
                        else:
                            skipped_count += 1
                    elif choice == "cancel":
                        print("Migration cancelled by user.")
                        break
                continue

            if self._create_config(target_api, cfg):
                migrated_count += 1
            else:
                skipped_count += 1

        print(
            f"Migration complete. Found {source_count} source application configs, "
            f"migrated {migrated_count}, updated {updated_count}, skipped {skipped_count}."
        )
        return {
            "source": source_count,
            "migrated": migrated_count,
            "updated": updated_count,
            "skipped": skipped_count,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_configs(
        self, api: ApplicationSettingsApi, label: str
    ) -> Optional[List[ApplicationConfig]]:
        """Retrieve all application configs from a backend.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of ApplicationConfig objects or None on failure.
        """
        try:
            configs = api.get_application_configs()
            print(f"Fetched {len(configs)} application configs from {label}.")
            return configs
        except Exception as e:
            print(f"Error fetching {label} application configs: {e}")
            return None

    def _create_config(
        self, api: ApplicationSettingsApi, cfg: ApplicationConfig
    ) -> bool:
        """Create a new application config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source ApplicationConfig to create.

        Returns:
            True on success, False otherwise.
        """
        try:
            payload = NewApplicationConfig(
                accessRules=cfg.access_rules,
                boundaryScope=cfg.boundary_scope,
                businessCriticality=cfg.business_criticality,
                label=cfg.label,
                matchSpecification=cfg.match_specification,
                scope=cfg.scope,
                tagFilterExpression=cfg.tag_filter_expression,
            )
            result = api.add_application_config(payload)
            print(f"✓ Migrated application config '{cfg.label}' (Target ID: {result.id})")
            return True
        except Exception as e:
            print(f"✗ Failed to migrate application config '{cfg.label}': {e}")
            return False

    def _update_config(
        self,
        api: ApplicationSettingsApi,
        cfg: ApplicationConfig,
        target_configs: List[ApplicationConfig],
    ) -> bool:
        """Update an existing application config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source ApplicationConfig whose content should be written.
            target_configs: List of existing target configs (used to look up the target ID).

        Returns:
            True on success, False otherwise.
        """
        target = next((t for t in target_configs if t.label == cfg.label), None)
        if target is None:
            print(f"✗ Could not find target application config '{cfg.label}' for update.")
            return False
        try:
            # PUT expects the full ApplicationConfig including the target's id
            updated_cfg = ApplicationConfig(
                id=target.id,
                accessRules=cfg.access_rules,
                boundaryScope=cfg.boundary_scope,
                businessCriticality=cfg.business_criticality,
                label=cfg.label,
                matchSpecification=cfg.match_specification,
                scope=cfg.scope,
                tagFilterExpression=cfg.tag_filter_expression,
            )
            result = api.put_application_config(target.id, updated_cfg)
            print(f"✓ Updated application config '{cfg.label}' (Target ID: {result.id})")
            return True
        except Exception as e:
            print(f"✗ Failed to update application config '{cfg.label}': {e}")
            return False

    def _prompt_duplicate(self, label: str) -> str:
        """Prompt the user for an action when a duplicate is found.

        Args:
            label: Name of the duplicate config.

        Returns:
            One of 'skip', 'update', or 'cancel'.
        """
        if not sys.stdin.isatty():
            print(f"Non-interactive mode: skipping duplicate '{label}'.")
            return "skip"

        while True:
            print(f"\nApplication config '{label}' already exists in the target.")
            print("  [s] Skip")
            print("  [u] Update existing config")
            print("  [c] Cancel migration")
            choice = input("Enter your choice [s/u/c]: ").strip().lower()
            if choice in ("s", "skip"):
                return "skip"
            elif choice in ("u", "update"):
                return "update"
            elif choice in ("c", "cancel"):
                return "cancel"
            print("Invalid choice. Please try again.")
