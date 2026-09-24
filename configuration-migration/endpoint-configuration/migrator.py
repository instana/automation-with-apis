"""Core functionality for migrating endpoint configurations between backends.

Migrates endpoint configs (custom endpoint mapping rules per service) using the instana_client SDK.

Note: EndpointConfig is scoped to a service via `serviceId`.  Because service IDs are
backend-specific, this migrator copies endpoint configs keyed on `serviceId` — if a
matching config already exists in the target for the same service ID it will be treated
as a duplicate.  In most cross-backend migration scenarios the service IDs will differ;
consider using the `--on-duplicate update` flag if you are migrating between environments
that share the same service IDs (e.g. staging → production restores).

When using file source the JSON file must contain a list of endpoint config objects,
each with at minimum a ``serviceId`` field and optionally ``endpointCase``, ``rules``,
``endpointNameByCollectedPathTemplateRuleEnabled``, and
``endpointNameByFirstPathSegmentRuleEnabled``.
"""

import sys
import os
import json
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config
from utils import MigrationResult, build_api, check_permissions, dry_run_connectivity_check, empty_result, make_result, partial_result, print_api_error, print_dry_run_preview, prompt_duplicate

_REQUIRED_PERMISSIONS = ["canConfigureServiceMapping"]

from typing import Dict, List, Optional

from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.models.endpoint_config import EndpointConfig


class EndpointConfigMigrator:
    """Handles migration of endpoint configurations between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details.
        """
        self.config = config
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> MigrationResult:
        """Perform the migration of endpoint configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, and skipped configs.
        """
        self.config.validate()

        if self.config.dry_run:
            return self._dry_run()

        if not check_permissions(self.config, _REQUIRED_PERMISSIONS):
            return empty_result()

        print("Starting migration of endpoint configurations...")

        target_api = build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )

        source_configs = self._get_source_configs()
        if source_configs is None:
            return empty_result()

        target_configs = self._get_configs(target_api, "target")
        if target_configs is None:
            return partial_result(len(source_configs))

        # Index target configs by serviceId for fast lookup
        target_by_service_id: Dict[str, EndpointConfig] = {
            cfg.service_id: cfg for cfg in target_configs
        }

        migrated_count = 0
        updated_count = 0
        skipped_count = 0
        source_count = len(source_configs)

        for cfg in source_configs:
            service_id = cfg.service_id

            if service_id in target_by_service_id:
                if self.config.on_duplicate == "update":
                    print(
                        f"⟳ Endpoint config for service '{service_id}' already exists, updating..."
                    )
                    if self._update_config(target_api, cfg, target_by_service_id[service_id]):
                        updated_count += 1
                    else:
                        skipped_count += 1
                elif self.config.on_duplicate == "skip":
                    print(
                        f"⊘ Endpoint config for service '{service_id}' already exists, skipping..."
                    )
                    skipped_count += 1
                else:
                    choice = prompt_duplicate("Endpoint config for service", service_id)
                    if choice == "skip":
                        skipped_count += 1
                    elif choice == "update":
                        if self._update_config(
                            target_api, cfg, target_by_service_id[service_id]
                        ):
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
            f"Migration complete. Found {source_count} source endpoint configs, "
            f"migrated {migrated_count}, updated {updated_count}, skipped {skipped_count}."
        )
        return make_result(source_count, migrated_count, updated_count, skipped_count)

    def _dry_run(self) -> MigrationResult:
        """Preview what would happen during migration without making any changes.

        Returns:
            Dictionary with would-be counts using the same keys as migrate().
        """
        target_api = build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )
        source_configs, target_configs = dry_run_connectivity_check(
            self.config,
            fetch_source=self._get_source_configs,
            fetch_target=lambda: self._get_configs(target_api, "target"),
            entity_name="endpoint configs",
            required_permissions=_REQUIRED_PERMISSIONS,
        )
        if source_configs is None:
            return empty_result()
        if target_configs is None:
            return partial_result(len(source_configs))

        target_by_service_id: Dict[str, EndpointConfig] = {
            cfg.service_id: cfg for cfg in target_configs
        }

        would_create = 0
        would_update = 0
        skipped_invalid = 0
        create_lines: list = []
        update_lines: list = []
        skip_lines: list = []

        for cfg in source_configs:
            service_id = cfg.service_id
            if not service_id:
                skip_lines.append("  ✗ Would skip    (endpoint config with missing service ID)")
                skipped_invalid += 1
                continue
            if service_id in target_by_service_id:
                update_lines.append(
                    f"  ~ Would update  endpoint config for service '{service_id}' (exists in target)"
                )
                would_update += 1
            else:
                create_lines.append(
                    f"  ✓ Would create  endpoint config for service '{service_id}'"
                )
                would_create += 1

        skipped_total = skipped_invalid
        print_dry_run_preview(
            create_lines, update_lines, skip_lines,
            source_count=len(source_configs),
            target_count=len(target_configs),
            would_create=would_create,
            would_update=would_update,
            skipped_total=skipped_total,
            skipped_detail=f"{skipped_invalid} invalid",
            entity_name="endpoint configs",
        )
        return make_result(len(source_configs), would_create, would_update, skipped_total)

    def _get_source_configs(self) -> Optional[List[EndpointConfig]]:
        """Get endpoint configs from a local JSON file or the source API.

        Returns:
            List of EndpointConfig objects or None on failure.
        """
        if self.config.events_source.lower() == "file":
            file_path = self.config.events_file_path
            try:
                print(f"Reading endpoint configs from {file_path}...")
                with open(file_path, 'r') as f:
                    items = json.load(f)
                if not isinstance(items, list):
                    print(f"Error: expected a JSON array in {file_path}")
                    return None
                configs = []
                for item in items:
                    if item.get("endpointCase") is None:
                        item["endpointCase"] = "ORIGINAL"
                    if item.get("rules") == []:
                        item["rules"] = None
                    configs.append(EndpointConfig.from_dict(item))
                print(f"Successfully loaded {len(configs)} endpoint configs from file")
                return configs
            except (FileNotFoundError, json.JSONDecodeError) as e:
                print(f"Error reading {file_path}: {e}")
                return None
        else:
            source_api = build_api(
                self.config.source_url, self.config.source_token, self.config.verify_ssl
            )
            configs = self._get_configs(source_api, "source")
            if configs is not None:
                try:
                    with open(self.config.events_file_path, 'w') as f:
                        json.dump([c.to_dict() for c in configs], f, indent=2)
                except OSError as e:
                    print(f"Warning: could not write {self.config.events_file_path}: {e}")
            return configs

    def _get_configs(
        self, api: ApplicationSettingsApi, label: str
    ) -> Optional[List[EndpointConfig]]:
        """Retrieve all endpoint configs from a backend.

        Fetches raw JSON to work around two SDK validation issues present in
        some Instana backends:
          - ``endpointCase`` may be ``null`` even though the model declares it
            as a non-optional ``StrictStr``.  We default it to ``"ORIGINAL"``.
          - ``rules`` may be an empty list ``[]`` even though the model requires
            ``min_length=1``.  We normalise empty lists to ``None`` so the field
            is treated as absent.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of EndpointConfig objects or None on failure.
        """
        try:
            raw = api.get_endpoint_configs_without_preload_content()
            items = json.loads(raw.read())
            if not isinstance(items, list):
                print(f"Error fetching {label} endpoint configs: unexpected response (not a list): {items}")
                return None
            configs = []
            for item in items:
                if item.get("endpointCase") is None:
                    item["endpointCase"] = "ORIGINAL"
                if item.get("rules") == []:
                    item["rules"] = None
                configs.append(EndpointConfig.from_dict(item))
            print(f"Fetched {len(configs)} endpoint configs from {label}.")
            return configs
        except Exception as e:
            print(f"Error fetching {label} endpoint configs: {e}")
            return None

    def _create_config(self, api: ApplicationSettingsApi, cfg: EndpointConfig) -> bool:
        """Create a new endpoint config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source EndpointConfig to create.

        Returns:
            True on success, False otherwise.
        """
        try:
            payload = EndpointConfig(
                endpointCase=cfg.endpoint_case,
                endpointNameByCollectedPathTemplateRuleEnabled=(
                    cfg.endpoint_name_by_collected_path_template_rule_enabled
                ),
                endpointNameByFirstPathSegmentRuleEnabled=(
                    cfg.endpoint_name_by_first_path_segment_rule_enabled
                ),
                rules=cfg.rules,
                serviceId=cfg.service_id,
            )
            result = api.create_endpoint_config(payload)
            print(
                f"✓ Migrated endpoint config for service '{cfg.service_id}' "
                f"(Target service ID: {result.service_id})"
            )
            return True
        except Exception as e:
            print(f"✗ Failed to migrate endpoint config for service '{cfg.service_id}': {e}")
            return False

    def _update_config(
        self,
        api: ApplicationSettingsApi,
        cfg: EndpointConfig,
        target_cfg: EndpointConfig,
    ) -> bool:
        """Update an existing endpoint config on the target backend.

        Args:
            api: Target ApplicationSettingsApi client.
            cfg: Source EndpointConfig whose settings should be written.
            target_cfg: The existing target EndpointConfig (provides the target service ID).

        Returns:
            True on success, False otherwise.
        """
        try:
            updated = EndpointConfig(
                endpointCase=cfg.endpoint_case,
                endpointNameByCollectedPathTemplateRuleEnabled=(
                    cfg.endpoint_name_by_collected_path_template_rule_enabled
                ),
                endpointNameByFirstPathSegmentRuleEnabled=(
                    cfg.endpoint_name_by_first_path_segment_rule_enabled
                ),
                rules=cfg.rules,
                serviceId=target_cfg.service_id,
            )
            result = api.update_endpoint_config(target_cfg.service_id, updated)
            print(
                f"✓ Updated endpoint config for service '{cfg.service_id}' "
                f"(Target service ID: {result.service_id})"
            )
            return True
        except Exception as e:
            print(
                f"✗ Failed to update endpoint config for service '{cfg.service_id}': {e}"
            )
            return False

