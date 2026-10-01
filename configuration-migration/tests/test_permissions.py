"""Unit tests for the permissions module."""

import pytest
import requests
from unittest.mock import patch, MagicMock, call
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from permissions import (
    check_destination_permissions,
    check_permissions,
    dry_run_connectivity_check,
    DryRunAbortedError,
)


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


    @patch("permissions.requests.get")
    def test_list_returns_non_json_raises(self, mock_get):
        """List endpoint returns 200 but non-JSON body → PermissionError."""
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.side_effect = ValueError("no JSON")
        mock_get.return_value = list_response

        with pytest.raises(PermissionError, match="non-JSON"):
            check_destination_permissions(config, ["canConfigureEventsAndAlerts"])


class TestCheckPermissions:
    """Tests for check_permissions() — the convenience bool wrapper."""

    @patch("permissions.requests.get")
    def test_returns_true_on_success(self, mock_get, capsys):
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [_token_entry(canConfigureEventsAndAlerts=True)]
        mock_get.return_value = list_response

        result = check_permissions(config, ["canConfigureEventsAndAlerts"])
        assert result is True
        # No error output expected
        assert capsys.readouterr().out == ""

    @patch("permissions.requests.get")
    def test_returns_false_and_prints_on_failure(self, mock_get, capsys):
        config = _make_config()

        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = [_token_entry(canConfigureEventsAndAlerts=False)]
        mock_get.return_value = list_response

        result = check_permissions(config, ["canConfigureEventsAndAlerts"])
        assert result is False
        out = capsys.readouterr().out
        assert "Permission check failed" in out
        assert "Migration aborted" in out

    @patch("permissions.requests.get")
    def test_returns_false_on_network_error(self, mock_get, capsys):
        config = _make_config()
        mock_get.side_effect = requests.ConnectionError("refused")

        result = check_permissions(config, ["canConfigureEventsAndAlerts"])
        assert result is False
        assert "Permission check failed" in capsys.readouterr().out


class TestDryRunConnectivityCheck:
    """Tests for dry_run_connectivity_check()."""

    def _make_config(self):
        return _make_config()

    def test_success_returns_source_and_target(self, capsys):
        source = [{"id": "s1"}]
        target = [{"id": "t1"}, {"id": "t2"}]

        with patch("permissions.check_destination_permissions") as mock_perm:
            s, t = dry_run_connectivity_check(
                _make_config(),
                fetch_source=lambda: source,
                fetch_target=lambda: target,
                entity_name="configs",
                required_permissions=["canConfigureEventsAndAlerts"],
            )
        assert s is source
        assert t is target
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "Step 1" in out
        assert "Step 2" in out

    def test_source_fetch_returns_none_raises(self, capsys):
        with pytest.raises(DryRunAbortedError, match="source"):
            dry_run_connectivity_check(
                _make_config(),
                fetch_source=lambda: None,
                fetch_target=lambda: [],
                entity_name="configs",
                required_permissions=[],
            )
        assert "Aborting" in capsys.readouterr().out

    def test_target_fetch_returns_none_raises(self, capsys):
        with pytest.raises(DryRunAbortedError, match="destination"):
            dry_run_connectivity_check(
                _make_config(),
                fetch_source=lambda: [],
                fetch_target=lambda: None,
                entity_name="configs",
                required_permissions=[],
            )
        assert "Aborting" in capsys.readouterr().out

    @patch("permissions.check_destination_permissions")
    def test_permission_check_failure_raises(self, mock_perm, capsys):
        mock_perm.side_effect = PermissionError("missing canX")

        with pytest.raises(DryRunAbortedError):
            dry_run_connectivity_check(
                _make_config(),
                fetch_source=lambda: [{}],
                fetch_target=lambda: [{}],
                entity_name="configs",
                required_permissions=["canX"],
            )
        out = capsys.readouterr().out
        assert "missing canX" in out
        assert "Aborting" in out
