"""Core functionality for migrating application configurations between backends.

Migrates Application Perspectives (application configs) using the instana_client SDK.
"""

import sys
import os
import json
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config
from utils import MigrationResult, build_api, check_permissions, dry_run_connectivity_check, empty_result, make_result, partial_result, print_api_error, print_dry_run_preview, prompt_duplicate
from permissions import check_destination_permissions

_REQUIRED_PERMISSIONS = ["canConfigureApplications"]

from typing import Dict, List, Optional

from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.exceptions import ApiException
from instana_client.models.application_config import ApplicationConfig
from instana_client.models.new_application_config import NewApplicationConfig

# Older Instana backends encode businessCriticality as an integer.
# Map those legacy values to the string enum the SDK expects (read path).
_BUSINESS_CRITICALITY_INT_TO_STR: Dict[int, str] = {
    0: "NOT_DEFINED",
    1: "LOWEST",
    2: "LOW",
    3: "MEDIUM",
    4: "HIGH",
    5: "HIGHEST",
}

# Reverse map for the write path — older targets expect an integer.
_BUSINESS_CRITICALITY_STR_TO_INT: Dict[str, int] = {
    v: k for k, v in _BUSINESS_CRITICALITY_INT_TO_STR.items()
}


class ApplicationConfigMigrator:
    """Handles migration of application configurations (Application Perspectives) between backends."""

    def __init__(self, config: Config):
        """Initialize the migrator with configuration.

        Args:
            config: Configuration object with backend details.
        """
        self.config = config
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def migrate(self) -> MigrationResult:
        """Perform the migration of application configurations.

        Returns:
            Dictionary with counts of source, migrated, updated, and skipped configs.
        """
        self.config.validate()

        if self.config.dry_run:
            return self._dry_run()

        if not check_permissions(self.config, _REQUIRED_PERMISSIONS):
            return empty_result()

        print("Starting migration of application configurations...")

        target_api = build_api(
            self.config.target_url, self.config.target_token, self.config.verify_ssl
        )

        source_configs = self._get_source_configs()
        if source_configs is None:
            return empty_result()

        target_configs = self._get_configs(target_api, "target")
        if target_configs is None:
            return partial_result(len(source_configs))

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
                    choice = prompt_duplicate("Application config", label)
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
            entity_name="application configs",
            required_permissions=_REQUIRED_PERMISSIONS,
        )
        if source_configs is None:
            return empty_result()
        if target_configs is None:
            return partial_result(len(source_configs))

        target_labels = {cfg.label for cfg in target_configs}

        would_create = 0
        would_update = 0
        skipped_invalid = 0
        create_lines: list = []
        update_lines: list = []
        skip_lines: list = []

        for cfg in source_configs:
            label = cfg.label
            if not label:
                skip_lines.append("  ✗ Would skip    (application config with missing label)")
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
            source_count=len(source_configs),
            target_count=len(target_configs),
            would_create=would_create,
            would_update=would_update,
            skipped_total=skipped_total,
            skipped_detail=f"{skipped_invalid} invalid",
            entity_name="application configs",
        )
        return make_result(len(source_configs), would_create, would_update, skipped_total)

    def _get_source_configs(self) -> Optional[List[ApplicationConfig]]:
        """Get application configs from a local JSON file or the source API.

        Returns:
            List of ApplicationConfig objects or None on failure.
        """
        if self.config.events_source.lower() == "file":
            file_path = self.config.events_file_path
            try:
                print(f"Reading application configs from {file_path}...")
                with open(file_path, 'r') as f:
                    items = json.load(f)
                if not isinstance(items, list):
                    print(f"Error: expected a JSON array in {file_path}")
                    return None
                for item in items:
                    bc = item.get("businessCriticality")
                    if isinstance(bc, int):
                        item["businessCriticality"] = _BUSINESS_CRITICALITY_INT_TO_STR.get(bc)
                    tfe = item.get("tagFilterExpression")
                    if isinstance(tfe, dict):
                        self._normalize_tag_filter(tfe)
                configs = [ApplicationConfig.from_dict(item) for item in items]
                print(f"Successfully loaded {len(configs)} application configs from file")
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

    @staticmethod
    def _normalize_tag_filter(node: dict) -> None:
        """Coerce integer ``value`` fields in TagFilter nodes to strings in-place.

        The Instana API occasionally returns tag filter values as integers
        (e.g. HTTP status code ``200``).  The SDK's ``TagFilterAllOfValue``
        ``oneOf`` validator rejects integers because they match both the ``int``
        and ``float`` schemas simultaneously.  Casting to ``str`` here ensures
        only the ``str`` schema matches.

        ``tagFilterExpression`` is a recursive tree whose leaves are
        ``TagFilter`` nodes (``type == "TAG_FILTER"``); internal nodes are
        ``TagFilterExpression`` nodes that carry an ``elements`` list.
        """
        if not isinstance(node, dict):
            return
        node_type = node.get("type")
        if node_type == "TAG_FILTER":
            if isinstance(node.get("value"), int):
                node["value"] = str(node["value"])
        # Recurse into child elements (TagFilterExpression nodes)
        for element in node.get("elements", []):
            ApplicationConfigMigrator._normalize_tag_filter(element)

    def _get_configs(
        self, api: ApplicationSettingsApi, label: str
    ) -> Optional[List[ApplicationConfig]]:
        """Retrieve all application configs from a backend.

        Fetches raw JSON so that two quirks of older Instana backends are
        handled before pydantic strict validation runs:
          - ``businessCriticality`` may be an integer; coerce to string enum.
          - ``tagFilterExpression`` leaf nodes may carry integer ``value``
            fields (e.g. HTTP status ``200``); coerce to string so the SDK's
            ``TagFilterAllOfValue`` oneOf validator matches only ``str``.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of ApplicationConfig objects or None on failure.
        """
        try:
            raw = api.get_application_configs_without_preload_content()
            items = json.loads(raw.read())
            if not isinstance(items, list):
                print(f"Error fetching {label} application configs: unexpected response (not a list): {items}")
                return None
            for item in items:
                bc = item.get("businessCriticality")
                if isinstance(bc, int):
                    item["businessCriticality"] = _BUSINESS_CRITICALITY_INT_TO_STR.get(bc)
                tfe = item.get("tagFilterExpression")
                if isinstance(tfe, dict):
                    self._normalize_tag_filter(tfe)
            configs = [ApplicationConfig.from_dict(item) for item in items]
            print(f"Fetched {len(configs)} application configs from {label}.")
            return configs
        except Exception as e:
            print(f"Error fetching {label} application configs: {e}")
            return None

    def _build_config_payload(self, cfg: ApplicationConfig) -> dict:
        """Serialise an ApplicationConfig to a plain dict ready for the REST API.

        Converts ``businessCriticality`` back to an integer when the value is
        a string enum, so that older target backends (which expect integers) are
        handled correctly.

        Args:
            cfg: Source ApplicationConfig to serialise.

        Returns:
            Dict suitable for use as a JSON request body.
        """
        bc = cfg.business_criticality
        if isinstance(bc, str):
            bc = _BUSINESS_CRITICALITY_STR_TO_INT.get(bc, bc)

        access_rules = (
            [r.to_dict() for r in cfg.access_rules] if cfg.access_rules else []
        )
        payload: dict = {
            "accessRules": access_rules,
            "boundaryScope": cfg.boundary_scope,
            "businessCriticality": bc,
            "label": cfg.label,
            "scope": cfg.scope,
        }
        if cfg.match_specification is not None:
            payload["matchSpecification"] = cfg.match_specification.to_dict()
        if cfg.tag_filter_expression is not None:
            payload["tagFilterExpression"] = cfg.tag_filter_expression.to_dict()
        return payload

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
            payload = self._build_config_payload(cfg)
            raw = api.add_application_config_without_preload_content.__wrapped__(
                api, new_application_config=payload,
            )
            body = raw.read()
            target_id = None
            if body:
                try:
                    target_id = json.loads(body).get('id')
                except Exception:
                    pass
            id_str = f"Target ID: {target_id}" if target_id else "created"
            print(f"✓ Migrated application config '{cfg.label}' ({id_str})")
            return True
        except ApiException as e:
            print_api_error(f"✗ Failed to migrate application config '{cfg.label}'", e)
            return False
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
            payload = self._build_config_payload(cfg)
            payload["id"] = target.id
            raw = api.put_application_config_without_preload_content.__wrapped__(
                api, id=target.id, application_config=payload,
            )
            body = raw.read()
            target_id = None
            if body:
                try:
                    target_id = json.loads(body).get('id')
                except Exception:
                    pass
            id_str = f"Target ID: {target_id}" if target_id else f"Target ID: {target.id}"
            print(f"✓ Updated application config '{cfg.label}' ({id_str})")
            return True
        except ApiException as e:
            print_api_error(f"✗ Failed to update application config '{cfg.label}'", e)
            return False
        except Exception as e:
            print(f"✗ Failed to update application config '{cfg.label}': {e}")
            return False

