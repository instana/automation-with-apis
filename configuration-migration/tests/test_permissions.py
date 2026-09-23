"""Unit tests for the check_destination_permissions helper."""

import pytest
import requests
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permissions import check_destination_permissions


# Real token value passed via --target-token
_FULL_TOKEN = "my-secret-tokenXYZ"
# How the API returns it in the list response (prefix + asterisks)
_MASKED_TOKEN = "my-secr******************"


def _make_config(target_token=_FULL_TOKEN, target_url="https://target.example.com"):
    config = MagicMock()
    config.target_token = target_token
    config.target_url = target_url
    config.verify_ssl = True
    config.get_target_headers.return_value = {
        "Authorization": f"apiToken {target_token}",
        "Content-Type": "application/json",
    }
    return config


def _token_entry(**permissions):
    """Build a minimal list-response token entry with masked token values, as the real API returns."""
    return {
        "id": _MASKED_TOKEN,
        "accessGrantingToken": _MASKED_TOKEN,
        "internalId": "abc-123",
        "name": "my token",
        **permissions,
    }


class TestCheckDestinationPermissions:
    """Tests for check_destination_permissions."""

    @patch("permissions.requests.get")
    def test_all_permissions_present_passes(self, mock_get):
        """Happy path: token found in list, all required permissions are True."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [
            _token_entry(
                canConfigureEventsAndAlerts=True,
                canConfigureMaintenanceWindows=True,
            )
        ]
        mock_get.return_value = list_response

        # Should not raise
        check_destination_permissions(
            config, ["canConfigureEventsAndAlerts", "canConfigureMaintenanceWindows"]
        )

        # Only one call — the list endpoint; no detail call needed
        assert mock_get.call_count == 1
        assert mock_get.call_args_list[0][0][0] == "https://target.example.com/api/settings/api-tokens"

    @patch("permissions.requests.get")
    def test_missing_permission_raises(self, mock_get):
        """Token found but a required permission is False → PermissionError."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [
            _token_entry(
                canConfigureEventsAndAlerts=False,
                canConfigureMaintenanceWindows=True,
            )
        ]
        mock_get.return_value = list_response

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(
                config, ["canConfigureEventsAndAlerts", "canConfigureMaintenanceWindows"]
            )

        assert "canConfigureEventsAndAlerts" in str(exc_info.value)
        assert "missing required permissions" in str(exc_info.value)

    @patch("permissions.requests.get")
    def test_absent_permission_field_treated_as_missing(self, mock_get):
        """A required field absent from the entry (defaults to None via .get()) is treated as missing."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        # canConfigureEventsAndAlerts not present in the entry at all
        list_response.json.return_value = [_token_entry()]
        mock_get.return_value = list_response

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])

        assert "canConfigureEventsAndAlerts" in str(exc_info.value)

    @patch("permissions.requests.get")
    def test_multiple_tokens_correct_one_matched(self, mock_get):
        """When multiple tokens exist in the list, the correct one is matched by masked prefix."""
        config = _make_config(target_token=_FULL_TOKEN)

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [
            # A different token that has the permission (different prefix)
            {
                "id": "zzzzz******************",
                "accessGrantingToken": "zzzzz******************",
                "internalId": "other-internal",
                "canConfigureEventsAndAlerts": True,
            },
            # Our token that does NOT have the permission
            _token_entry(canConfigureEventsAndAlerts=False),
        ]
        mock_get.return_value = list_response

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])

        # Must have checked our token, not the other one
        assert "canConfigureEventsAndAlerts" in str(exc_info.value)
        assert "missing required permissions" in str(exc_info.value)

    @patch("permissions.requests.get")
    def test_list_request_non_200_raises(self, mock_get):
        """List endpoint returns non-200 (e.g. 403 for missing canConfigureApiTokens) → PermissionError."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 403
        list_response.text = "Forbidden"
        mock_get.return_value = list_response

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])

        assert "403" in str(exc_info.value)
        assert mock_get.call_count == 1

    @patch("permissions.requests.get")
    def test_list_request_network_error_raises(self, mock_get):
        """Network failure on list request → PermissionError."""
        config = _make_config()
        mock_get.side_effect = requests.ConnectionError("connection refused")

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])

        assert "Failed to reach" in str(exc_info.value)

    @patch("permissions.requests.get")
    def test_token_not_found_in_list_raises(self, mock_get):
        """No prefix match in list response → PermissionError."""
        # Full token starts with "secret"; masked entry has a different prefix
        config = _make_config(target_token="secretXYZ")

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [
            {"accessGrantingToken": "zzzzz******************", "internalId": "xyz"}
        ]
        mock_get.return_value = list_response

        with pytest.raises(PermissionError) as exc_info:
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])

        assert "not found" in str(exc_info.value)
        assert mock_get.call_count == 1

    @patch("permissions.requests.get")
    def test_empty_required_fields_passes(self, mock_get):
        """Empty required_fields → token found, nothing to check, passes."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [_token_entry()]
        mock_get.return_value = list_response

        # Should not raise
        check_destination_permissions(config, [])
        assert mock_get.call_count == 1
