"""Core functionality for migrating service configurations between backends.

Migrates custom service rules (service configs) using the instana_client SDK.
"""

import sys
import os
import json
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config import Config

from typing import Dict, List, Optional

import instana_client
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.exceptions import ApiException
from instana_client.models.service_config import ServiceConfig


def _print_api_error(prefix: str, e: ApiException) -> None:
    """Print a concise error message from an ApiException.

    Extracts just the HTTP status and the response body (which typically
    contains the server-side error detail) rather than dumping full headers.

    Args:
        prefix: Message prefix, e.g. "✗ Failed to migrate config 'foo'".
        e: The ApiException to summarise.
    """
    body = e.body or ""
    try:
        parsed = json.loads(body)
        detail = parsed.get("details") or parsed.get("message") or body
    except Exception:
        detail = body
    print(f"{prefix}: HTTP {e.status} - {detail}")


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
            _print_api_error(f"✗ Failed to migrate service config '{cfg.name}'", e)
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
            _print_api_error(f"✗ Failed to update service config '{cfg.name}'", e)
            return False
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
