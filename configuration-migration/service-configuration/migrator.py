"""Core functionality for migrating service configurations between backends.

Migrates custom service rules (service configs) using the instana_client SDK.
"""

import sys
import os
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config

from typing import Dict, List, Optional

import instana_client
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.models.service_config import ServiceConfig


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


class ServiceConfigMigrator:
    """Handles migration of custom service configurations between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details.
        """
        self.config = config
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> Dict[str, int]:
        """Perform the migration of service configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, and skipped configs.
        """
        self.config.validate()

        print("Starting migration of service configurations...")

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

        target_names = {cfg.name for cfg in target_configs}

        migrated_count = 0
        updated_count = 0
        skipped_count = 0
        source_count = len(source_configs)

        for cfg in source_configs:
            name = cfg.name

            if name in target_names:
                if self.config.on_duplicate == "update":
                    print(f"⟳ Service config '{name}' already exists, updating...")
                    if self._update_config(target_api, cfg, target_configs):
                        updated_count += 1
                    else:
                        skipped_count += 1
                elif self.config.on_duplicate == "skip":
                    print(f"⊘ Service config '{name}' already exists, skipping...")
                    skipped_count += 1
                else:
                    choice = self._prompt_duplicate(name)
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
            f"Migration complete. Found {source_count} source service configs, "
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
    ) -> Optional[List[ServiceConfig]]:
        """Retrieve all service configs from a backend.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of ServiceConfig objects or None on failure.
        """
        try:
            configs = api.get_service_configs()
            print(f"Fetched {len(configs)} service configs from {label}.")
            return configs
        except Exception as e:
            print(f"Error fetching {label} service configs: {e}")
            return None

    def _create_config(self, api: ApplicationSettingsApi, cfg: ServiceConfig) -> bool:
        """Create a new service config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source ServiceConfig to create.

        Returns:
            True on success, False otherwise.
        """
        try:
            # ServiceConfig is used directly for both create (POST) and update (PUT).
            # Strip the source id so the target generates its own.
            payload = ServiceConfig(
                comment=cfg.comment,
                enabled=cfg.enabled,
                id=cfg.id,
                label=cfg.label,
                matchSpecification=cfg.match_specification,
                name=cfg.name,
            )
            result = api.add_service_config(payload)
            print(f"✓ Migrated service config '{cfg.name}' (Target ID: {result.id})")
            return True
        except Exception as e:
            print(f"✗ Failed to migrate service config '{cfg.name}': {e}")
            return False

    def _update_config(
        self,
        api: ApplicationSettingsApi,
        cfg: ServiceConfig,
        target_configs: List[ServiceConfig],
    ) -> bool:
        """Update an existing service config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source ServiceConfig whose content should be written.
            target_configs: List of existing target configs (used to look up the target ID).

        Returns:
            True on success, False otherwise.
        """
        target = next((t for t in target_configs if t.name == cfg.name), None)
        if target is None:
            print(f"✗ Could not find target service config '{cfg.name}' for update.")
            return False
        try:
            updated_cfg = ServiceConfig(
                comment=cfg.comment,
                enabled=cfg.enabled,
                id=target.id,
                label=cfg.label,
                matchSpecification=cfg.match_specification,
                name=cfg.name,
            )
            result = api.put_service_config(target.id, updated_cfg)
            print(f"✓ Updated service config '{cfg.name}' (Target ID: {result.id})")
            return True
        except Exception as e:
            print(f"✗ Failed to update service config '{cfg.name}': {e}")
            return False

    def _prompt_duplicate(self, name: str) -> str:
        """Prompt the user for an action when a duplicate is found.

        Args:
            name: Name of the duplicate config.

        Returns:
            One of 'skip', 'update', or 'cancel'.
        """
        if not sys.stdin.isatty():
            print(f"Non-interactive mode: skipping duplicate '{name}'.")
            return "skip"

        while True:
            print(f"\nService config '{name}' already exists in the target.")
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
