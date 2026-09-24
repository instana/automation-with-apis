"""Shared permission-check helpers for all migrators.

This module owns all permission-related logic:
  - ``check_destination_permissions``: low-level raise-on-failure check.
  - ``check_permissions``: convenience wrapper that prints and returns bool.
  - ``dry_run_connectivity_check``: Steps 1 & 2 used by every _dry_run() method.
"""

import requests


def check_destination_permissions(config, required_fields: list[str]) -> None:
    """Verify that the destination API token has all required permissions.

    Calls GET /api/settings/api-tokens to list all tokens for the tenant.
    The list response includes the full ``canXYZ`` permission set for each
    token. The calling token is identified by matching ``accessGrantingToken``
    against ``config.target_token`` — that field holds the same value the user
    passes as ``--target-token``.

    If the list request returns a non-200 (e.g. 403), the token either lacks
    ``canConfigureApiTokens`` or is invalid, and we surface that directly.

    Args:
        config: Config instance with ``target_url``, ``target_token``,
                ``get_target_headers()``, and ``verify_ssl``.
        required_fields: List of ``canXYZ`` permission field names that must
                         all be ``True`` on the destination token.

    Raises:
        PermissionError: If the list request fails, the token is not found in
                         the list, or any required permission is missing.
    """
    headers = config.get_target_headers()
    list_url = f"{config.target_url}/api/settings/api-tokens"

    try:
        list_resp = requests.get(list_url, headers=headers, verify=config.verify_ssl)
    except requests.RequestException as exc:
        raise PermissionError(
            f"Failed to reach destination API tokens endpoint ({list_url}): {exc}"
        ) from exc

    if list_resp.status_code != 200:
        raise PermissionError(
            f"Destination API tokens list request failed with status "
            f"{list_resp.status_code}: {list_resp.text}"
        )

    try:
        tokens = list_resp.json()
    except ValueError as exc:
        raise PermissionError(
            f"Destination API tokens list returned non-JSON response: {exc}"
        ) from exc

    # The list endpoint masks token values — accessGrantingToken is returned
    # as e.g. "Q2b6TL0C******************" rather than the full token string.
    # Match by comparing the visible prefix (characters before the first '*')
    # against the start of the user-supplied token.
    def _token_prefix(masked: str) -> str:
        """Return the unmasked prefix from a masked token string."""
        return masked.split("*")[0]

    matched = next(
        (
            t for t in tokens
            if (agt := t.get("accessGrantingToken"))
            and _token_prefix(agt)
            and config.target_token.startswith(_token_prefix(agt))
        ),
        None,
    )
    if matched is None:
        raise PermissionError(
            "Destination API token not found in the token list. "
            "Ensure the configured target token is valid and active."
        )

    missing = [field for field in required_fields if not matched.get(field)]

    if missing:
        raise PermissionError(
            f"Destination API token is missing required permissions: "
            f"{', '.join(missing)}"
        )


def check_permissions(config, required_permissions: list[str]) -> bool:
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
    required_permissions: list[str],
) -> tuple[list | None, list | None]:
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
