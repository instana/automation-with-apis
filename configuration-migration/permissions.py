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

    # accessGrantingToken in the response equals the token value the user
    # passes as --target-token, so we can match directly.
    for i, t in enumerate(tokens):
        agt = t.get("accessGrantingToken", "<missing>")
        name = t.get("name", "<no name>")

    matched = next(
        (t for t in tokens if t.get("accessGrantingToken") == config.target_token),
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
