"""Shared permission-check helper for all migrators."""

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
