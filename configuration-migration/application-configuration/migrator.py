"""Core functionality for migrating application configurations between backends.

Migrates Application Perspectives (application configs) using the instana_client SDK.
"""

import sys
import os
import json
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config
from utils import MigrationResult, build_api, empty_result, make_result, partial_result, print_api_error, prompt_duplicate

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

        print("Starting migration of application configurations...")

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

    def _get_configs(
        self, api: ApplicationSettingsApi, label: str
    ) -> Optional[List[ApplicationConfig]]:
        """Retrieve all application configs from a backend.

        Fetches raw JSON so that legacy integer ``businessCriticality`` values
        (returned by older Instana backends) are coerced to their string enum
        equivalents before pydantic strict validation runs.

        Args:
            api: The ApplicationSettingsApi client to use.
            label: Human-readable label for logging ("source" or "target").

        Returns:
            List of ApplicationConfig objects or None on failure.
        """
        try:
            raw = api.get_application_configs_without_preload_content()
            items = json.loads(raw.read())
            for item in items:
                bc = item.get("businessCriticality")
                if isinstance(bc, int):
                    item["businessCriticality"] = _BUSINESS_CRITICALITY_INT_TO_STR.get(bc)
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

