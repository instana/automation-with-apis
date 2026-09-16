"""Shared utilities for configuration migration modules."""

import json
from typing import TypedDict

import sys

import instana_client
import urllib3
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.exceptions import ApiException


class MigrationResult(TypedDict):
    """Counts returned by every migrator's ``migrate()`` method."""

    source: int
    migrated: int
    updated: int
    skipped: int


def empty_result() -> MigrationResult:
    """Return a zero-valued MigrationResult (used when source fetch fails)."""
    return {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}


def partial_result(source: int) -> MigrationResult:
    """Return a MigrationResult with only source count set (used when target fetch fails)."""
    return {"source": source, "migrated": 0, "updated": 0, "skipped": 0}


def make_result(source: int, migrated: int, updated: int, skipped: int) -> MigrationResult:
    """Return a fully populated MigrationResult."""
    return {
        "source": source,
        "migrated": migrated,
        "updated": updated,
        "skipped": skipped,
    }


def prompt_duplicate(entity_type: str, name: str) -> str:
    """Prompt the user for an action when a duplicate config is found.

    Used by all interactive migrators when ``on_duplicate`` is not pre-set.
    Falls back to ``"skip"`` in non-interactive (non-TTY) environments.

    Args:
        entity_type: Human-readable label for the entity kind,
            e.g. ``"Service config"`` or ``"Application config"``.
        name: Name / identifier of the duplicate item.

    Returns:
        One of ``'skip'``, ``'update'``, or ``'cancel'``.
    """
    if not sys.stdin.isatty():
        print(f"Non-interactive mode: skipping duplicate '{name}'.")
        return "skip"

    while True:
        print(f"\n{entity_type} '{name}' already exists in the target.")
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


def build_api(url: str, token: str, verify_ssl: bool) -> ApplicationSettingsApi:
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


def print_api_error(prefix: str, e: ApiException) -> None:
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
