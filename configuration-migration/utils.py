"""Shared utilities for configuration migration modules."""

import json
from typing import List, Optional, Tuple, TypedDict

import sys

import instana_client
import urllib3
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.exceptions import ApiException


class MigrationResult(TypedDict):
    """Counts returned by every migrator's ``migrate()`` method.

    The ``skipped`` field is the total of all skip sub-categories:
      skipped_identical + skipped_unsafe + skipped_user + skipped_invalid

    Migrators that do not distinguish between skip reasons will only populate
    ``skipped`` and leave the sub-fields as 0.
    """

    source: int
    migrated: int
    updated: int
    # Rolled-up skip total (always equals sum of sub-fields below)
    skipped: int
    # Skip sub-categories — 0 when not applicable for a given migrator
    skipped_identical: int  # duplicate detected, content identical
    skipped_unsafe: int     # contains credentials / id references that cannot be migrated
    skipped_user: int       # user explicitly chose to skip at the interactive prompt
    skipped_invalid: int    # config is structurally invalid / unmigratable
    failed: int


def empty_result() -> MigrationResult:
    """Return a zero-valued MigrationResult (used when source fetch or permissions fail)."""
    return {
        "source": 0, "migrated": 0, "updated": 0,
        "skipped": 0, "skipped_identical": 0, "skipped_unsafe": 0,
        "skipped_user": 0, "skipped_invalid": 0, "failed": 0,
    }


def partial_result(source: int) -> MigrationResult:
    """Return a MigrationResult with only source count set (used when target fetch fails)."""
    return {
        "source": source, "migrated": 0, "updated": 0,
        "skipped": 0, "skipped_identical": 0, "skipped_unsafe": 0,
        "skipped_user": 0, "skipped_invalid": 0, "failed": 0,
    }


def make_result(
    source: int,
    migrated: int,
    updated: int,
    skipped: int = 0,
    failed: int = 0,
    skipped_identical: int = 0,
    skipped_unsafe: int = 0,
    skipped_user: int = 0,
    skipped_invalid: int = 0,
) -> MigrationResult:
    """Return a fully populated MigrationResult.

    ``skipped`` should equal the sum of all skipped_* sub-fields when they are
    provided.  For migrators that do not break down skip reasons, pass only
    ``skipped`` and leave the sub-fields at their default of 0.
    """
    return {
        "source": source,
        "migrated": migrated,
        "updated": updated,
        "skipped": skipped,
        "skipped_identical": skipped_identical,
        "skipped_unsafe": skipped_unsafe,
        "skipped_user": skipped_user,
        "skipped_invalid": skipped_invalid,
        "failed": failed,
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

def check_permissions(config, required_permissions: List[str]) -> bool:
    """Check that the destination API token has all required permissions.

    Intended to be called at the start of every ``migrate()`` run so that a
    missing permission is surfaced immediately with a clear message rather than
    discovered mid-migration when the first write call returns HTTP 403.

    Args:
        config: The Config instance (provides target_url, target_token, etc.).
        required_permissions: List of ``canXYZ`` permission keys that must all
            be ``True`` on the destination token.

    Returns:
        ``True`` if all permissions are present, ``False`` otherwise (after
        printing a human-readable error message).
    """
    from permissions import check_destination_permissions  # local import to avoid circular deps

    try:
        check_destination_permissions(config, required_permissions)
        return True
    except PermissionError as exc:
        print(f"✗ Permission check failed: {exc}")
        print("Migration aborted. Ensure the target API token has the required permissions and try again.")
        return False

def dry_run_connectivity_check(
    config,
    fetch_source,
    fetch_target,
    entity_name: str,
    required_permissions: List[str],
) -> Tuple[Optional[list], Optional[list]]:
    """Run the standard Steps 1 & 2 used by every _dry_run() method.

    Prints the connectivity and permission-check output that is identical
    across all migrators, and returns the fetched configs so the caller can
    proceed to Step 3 (compare).

    Args:
        config: The Config instance (provides source_url, target_url, etc.).
        fetch_source: Zero-argument callable that returns the source list or None.
        fetch_target: Zero-argument callable that returns the target list or None.
        entity_name: Plural human-readable label, e.g. ``"application configs"``.
        required_permissions: List of ``canXYZ`` permission keys to check on the
            destination token.

    Returns:
        ``(source_items, target_items)`` on full success.
        ``(None, None)`` if the source fetch failed.
        ``(source_items, None)`` if the target fetch or permission check failed.
    """
    from permissions import check_destination_permissions  # local import to avoid circular deps

    print("[DRY RUN] Starting dry-run preview — no changes will be made.\n")

    # --- Step 1: Connectivity ---
    print("[Step 1] Checking connectivity ...")
    print(f"  Source ({config.source_url}) ...")
    source_items = fetch_source()
    if source_items is None:
        print(f"  FAILED — could not fetch source {entity_name}.")
        print("[DRY RUN] Aborting.")
        return None, None
    print(f"  Source ... OK ({len(source_items)} {entity_name} found)")
    print(f"  Destination ({config.target_url}) ...")
    target_items = fetch_target()
    if target_items is None:
        print(f"  FAILED — could not fetch destination {entity_name}.")
        print("[DRY RUN] Aborting.")
        return source_items, None
    print(f"  Destination ... OK ({len(target_items)} {entity_name} found)\n")

    # --- Step 2: Permission check ---
    print("[Step 2] Verifying destination API token permissions ...")
    try:
        check_destination_permissions(config, required_permissions)
        print("  Required permissions check ... OK\n")
    except PermissionError as exc:
        print(f"  FAILED — {exc}")
        print("[DRY RUN] Aborting.")
        return source_items, None

    return source_items, target_items


def print_dry_run_preview(
    create_lines: List[str],
    update_lines: List[str],
    skip_lines: List[str],
    source_count: int,
    target_count: int,
    would_create: int,
    would_update: int,
    skipped_total: int,
    skipped_detail: str,
    entity_name: str,
) -> None:
    """Print the standard Step 3 preview table and dry-run summary.

    Prints the ``--- Preview ---`` block (create/update/skip lines) and the
    ``--- Dry-run summary ---`` table that is identical in structure across
    every migrator.

    Args:
        create_lines: Lines prefixed with ``✓ Would create``.
        update_lines: Lines prefixed with ``~ Would update``.
        skip_lines: Lines prefixed with ``✗ Would skip`` or ``= Would skip``.
        source_count: Total items fetched from the source.
        target_count: Total items currently in the target.
        would_create: Count of items that would be created.
        would_update: Count of items that would be updated.
        skipped_total: Total items that would be skipped.
        skipped_detail: Human-readable breakdown, e.g. ``"3 invalid"`` or
            ``"2 identical, 1 unsafe"``.  Shown in parentheses on the skip line.
        entity_name: Plural label used in the summary, e.g. ``"configs"``.
    """
    print("[Step 3] Comparing configurations ...")
    print("--- Preview ---")
    for line in create_lines:
        print(line)
    for line in update_lines:
        print(line)
    if skip_lines:
        print()
        for line in skip_lines:
            print(line)

    print(f"\n--- Dry-run summary ---")
    label_w = max(len(f"Source {entity_name}"), len(f"Target {entity_name} now")) + 2
    print(f"  {'Source ' + entity_name:<{label_w}}: {source_count}")
    print(f"  {'Target ' + entity_name + ' now':<{label_w}}: {target_count}")
    print(f"  {'Would be created':<{label_w}}: {would_create}")
    print(f"  {'Would be updated':<{label_w}}: {would_update}")
    print(f"  {'Would skip':<{label_w}}: {skipped_total}  ({skipped_detail})")
    print(f"\n  Target {entity_name} after migration would be: {target_count + would_create}")
    print("\n[DRY RUN] No changes were made.")


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
