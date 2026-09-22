"""Core functionality for migrating service configurations between backends.

Migrates custom service rules (service configs) using the instana_client SDK.
"""

import sys
import os
import json
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config
from utils import MigrationResult, build_api, empty_result, make_result, partial_result, print_api_error, prompt_duplicate

from typing import List, Optional

from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.exceptions import ApiException
from instana_client.models.service_config import ServiceConfig


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

    def migrate(self) -> MigrationResult:
        """Perform the migration of service configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, and skipped configs.
        """
        self.config.validate()

        if self.config.dry_run:
            return self._dry_run()

        print("Starting migration of service configurations...")

        source_api = build_api(
            self.config.source_url, self.config.source_token, self.config.verify_ssl
        )
        target_api = build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )

        source_configs = self._get_configs(source_api, "source")
        if source_configs is None:
            return empty_result()

        target_configs = self._get_configs(target_api, "target")
        if target_configs is None:
            return partial_result(len(source_configs))

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
                    choice = prompt_duplicate("Service config", name)
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
        return make_result(source_count, migrated_count, updated_count, skipped_count)

    def _dry_run(self) -> MigrationResult:
        """Preview what would happen during migration without making any changes.

        Returns:
            Dictionary with would-be counts using the same keys as migrate().
        """
        print("[DRY RUN] Starting dry-run preview — no changes will be made.\n")

        # --- Step 1: Connectivity ---
        print(f"[Step 1] Checking connectivity ...")
        print(f"  Source ({self.config.source_url}) ...")
        source_api = build_api(
            self.config.source_url, self.config.source_token, self.config.verify_ssl
        )
        target_api = build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )
        source_configs = self._get_configs(source_api, "source")
        if source_configs is None:
            print("  FAILED — could not fetch source service configs.")
            print("[DRY RUN] Aborting.")
            return empty_result()
        print(f"  Source ... OK ({len(source_configs)} configs found)")
        print(f"  Destination ({self.config.target_url}) ...")
        target_configs = self._get_configs(target_api, "target")
        if target_configs is None:
            print("  FAILED — could not fetch destination service configs.")
            print("[DRY RUN] Aborting.")
            return partial_result(len(source_configs))
        print(f"  Destination ... OK ({len(target_configs)} configs found)\n")

        # --- Step 2: Compare configurations ---
        print("[Step 2] Comparing configurations ...")

        target_names = {cfg.name for cfg in target_configs}

        would_create = 0
        would_update = 0
        skipped_invalid = 0

        create_lines = []
        update_lines = []

        for cfg in source_configs:
            name = cfg.name
            if name in target_names:
                update_lines.append(f"  ~ Would update  '{name}' (exists in target)")
                would_update += 1
            else:
                create_lines.append(f"  ✓ Would create  '{name}'")
                would_create += 1

        print("--- Preview ---")
        for line in create_lines:
            print(line)
        for line in update_lines:
            print(line)

        skipped_total = skipped_invalid
        print(f"\n--- Dry-run summary ---")
        print(f"  Source configs      : {len(source_configs)}")
        print(f"  Target configs now  : {len(target_configs)}")
        print(f"  Would be created    : {would_create}")
        print(f"  Would be updated    : {would_update}")
        print(f"  Would skip          : {skipped_total}")
        print(f"\n  Target configs after migration would be: {len(target_configs) + would_create}")
        print("\n[DRY RUN] No changes were made.")

        return make_result(len(source_configs), would_create, would_update, skipped_total)

    def _get_configs(
        self, api: ApplicationSettingsApi, label: str
    ) -> Optional[List[ServiceConfig]]:
        """Retrieve all service configs from a backend.

        Fetches raw JSON so that any backend quirks are handled before
        pydantic strict validation runs.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of ServiceConfig objects or None on failure.
        """
        try:
            raw = api.get_service_configs_without_preload_content()
            items = json.loads(raw.read())
            if not isinstance(items, list):
                print(f"Error fetching {label} service configs: unexpected response (not a list): {items}")
                return None
            configs = [ServiceConfig.from_dict(item) for item in items]
            print(f"Fetched {len(configs)} service configs from {label}.")
            return configs
        except Exception as e:
            print(f"Error fetching {label} service configs: {e}")
            return None

    def _build_config_payload(self, cfg: ServiceConfig) -> dict:
        """Serialise a ServiceConfig to a plain dict ready for the REST API.

        Args:
            cfg: Source ServiceConfig to serialise.

        Returns:
            Dict suitable for use as a JSON request body.
        """
        payload: dict = {
            "enabled": cfg.enabled,
            "label": cfg.label,
            "matchSpecification": [r.to_dict() for r in cfg.match_specification],
            "name": cfg.name,
        }
        if cfg.comment is not None:
            payload["comment"] = cfg.comment
        return payload

    def _create_config(self, api: ApplicationSettingsApi, cfg: ServiceConfig) -> bool:
        """Create a new service config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source ServiceConfig to create.

        Returns:
            True on success, False otherwise.
        """
        try:
            payload = self._build_config_payload(cfg)
            raw = api.add_service_config_without_preload_content.__wrapped__(
                api, service_config=payload,
            )
            body = raw.read()
            target_id = None
            if body:
                try:
                    target_id = json.loads(body).get("id")
                except Exception:
                    pass
            id_str = f"Target ID: {target_id}" if target_id else "created"
            print(f"✓ Migrated service config '{cfg.name}' ({id_str})")
            return True
        except ApiException as e:
            print_api_error(f"✗ Failed to migrate service config '{cfg.name}'", e)
            return False
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
            payload = self._build_config_payload(cfg)
            payload["id"] = target.id
            raw = api.put_service_config_without_preload_content.__wrapped__(
                api, id=target.id, service_config=payload,
            )
            body = raw.read()
            target_id = None
            if body:
                try:
                    target_id = json.loads(body).get("id")
                except Exception:
                    pass
            id_str = f"Target ID: {target_id}" if target_id else f"Target ID: {target.id}"
            print(f"✓ Updated service config '{cfg.name}' ({id_str})")
            return True
        except ApiException as e:
            print_api_error(f"✗ Failed to update service config '{cfg.name}'", e)
            return False
        except Exception as e:
            print(f"✗ Failed to update service config '{cfg.name}': {e}")
            return False

