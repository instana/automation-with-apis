"""Unit tests for the shared utils module."""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils import (
    build_api, print_api_error, empty_result, partial_result, make_result,
    prompt_duplicate, print_dry_run_preview,
)
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.api.application_alert_configuration_api import ApplicationAlertConfigurationApi
from instana_client.api.event_settings_api import EventSettingsApi
from instana_client.api.infrastructure_alert_configuration_api import InfrastructureAlertConfigurationApi
from instana_client.exceptions import ApiException


class TestUtils:
    """Test cases for utils.py helper functions."""

    def test_migration_result_helpers(self):
        """Test result helper functions."""
        assert empty_result() == {
            "source": 0, "migrated": 0, "updated": 0,
            "skipped": 0, "skipped_identical": 0, "skipped_unsafe": 0,
            "skipped_user": 0, "skipped_invalid": 0, "failed": 0,
        }
        assert partial_result(5) == {
            "source": 5, "migrated": 0, "updated": 0,
            "skipped": 0, "skipped_identical": 0, "skipped_unsafe": 0,
            "skipped_user": 0, "skipped_invalid": 0, "failed": 0,
        }
        assert make_result(10, 5, 2, 3) == {
            "source": 10, "migrated": 5, "updated": 2,
            "skipped": 3, "skipped_identical": 0, "skipped_unsafe": 0,
            "skipped_user": 0, "skipped_invalid": 0, "failed": 0,
        }

    @patch('instana_client.ApiClient')
    @patch('instana_client.Configuration')
    def test_build_api_default_cls(self, mock_config, mock_api_client):
        """Test build_api with default ApplicationSettingsApi."""
        client = build_api("https://test.instana.io", "test-token", True)
        assert isinstance(client, ApplicationSettingsApi)
        mock_config.assert_called_once_with(
            host="https://test.instana.io",
            api_key={"ApiKeyAuth": "test-token"},
            api_key_prefix={"ApiKeyAuth": "apiToken"},
        )

    @patch('instana_client.ApiClient')
    @patch('instana_client.Configuration')
    def test_build_api_custom_cls(self, mock_config, mock_api_client):
        """Test build_api with various SDK API classes."""
        app_alerts_api = build_api("https://test.instana.io", "test-token", False, ApplicationAlertConfigurationApi)
        assert isinstance(app_alerts_api, ApplicationAlertConfigurationApi)

        event_api = build_api("https://test.instana.io", "test-token", True, EventSettingsApi)
        assert isinstance(event_api, EventSettingsApi)

        infra_api = build_api("https://test.instana.io", "test-token", True, InfrastructureAlertConfigurationApi)
        assert isinstance(infra_api, InfrastructureAlertConfigurationApi)

    def test_print_api_error(self, capsys):
        """Test print_api_error formats output properly."""
        e = ApiException(status=404, reason="Not Found")
        e.body = '{"message": "Item missing"}'
        print_api_error("Error", e)
        captured = capsys.readouterr()
        assert "Error: HTTP 404 - Item missing" in captured.out

    def test_print_api_error_details_field(self, capsys):
        """print_api_error uses 'details' field when present."""
        e = ApiException(status=400, reason="Bad Request")
        e.body = '{"details": "field X invalid"}'
        print_api_error("✗ Failed", e)
        captured = capsys.readouterr()
        assert "field X invalid" in captured.out

    def test_print_api_error_non_json_body(self, capsys):
        """print_api_error handles non-JSON body gracefully."""
        e = ApiException(status=500, reason="Server Error")
        e.body = "plain text error"
        print_api_error("Prefix", e)
        captured = capsys.readouterr()
        assert "plain text error" in captured.out
        assert "HTTP 500" in captured.out

    def test_print_api_error_empty_body(self, capsys):
        """print_api_error handles None/empty body."""
        e = ApiException(status=503, reason="Unavailable")
        e.body = None
        print_api_error("Err", e)
        captured = capsys.readouterr()
        assert "HTTP 503" in captured.out


class TestPromptDuplicate:
    """Tests for prompt_duplicate()."""

    @patch("utils.sys.stdin.isatty", return_value=False)
    def test_non_interactive_returns_skip(self, mock_tty, capsys):
        result = prompt_duplicate("Service config", "my-service")
        assert result == "skip"
        out = capsys.readouterr().out
        assert "Non-interactive mode" in out
        assert "my-service" in out

    @patch("builtins.input", return_value="s")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_s_returns_skip(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "skip"

    @patch("builtins.input", return_value="skip")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_skip_word_returns_skip(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "skip"

    @patch("builtins.input", return_value="u")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_u_returns_update(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "update"

    @patch("builtins.input", return_value="update")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_update_word_returns_update(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "update"

    @patch("builtins.input", return_value="c")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_c_returns_cancel(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "cancel"

    @patch("builtins.input", return_value="cancel")
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_interactive_choice_cancel_word_returns_cancel(self, mock_tty, mock_input):
        result = prompt_duplicate("App config", "my-app")
        assert result == "cancel"

    @patch("builtins.input", side_effect=["invalid", "x", "s"])
    @patch("utils.sys.stdin.isatty", return_value=True)
    def test_invalid_input_retries_until_valid(self, mock_tty, mock_input, capsys):
        result = prompt_duplicate("App config", "my-app")
        assert result == "skip"
        # The "Invalid choice" line should have been printed twice
        out = capsys.readouterr().out
        assert out.count("Invalid choice") == 2


class TestPrintDryRunPreview:
    """Tests for print_dry_run_preview()."""

    def test_basic_output_structure(self, capsys):
        print_dry_run_preview(
            create_lines=["✓ Would create 'alpha'"],
            update_lines=["~ Would update 'beta'"],
            skip_lines=["✗ Would skip 'gamma'"],
            source_count=3,
            target_count=1,
            would_create=1,
            would_update=1,
            skipped_total=1,
            skipped_detail="1 identical",
            entity_name="configs",
        )
        out = capsys.readouterr().out
        assert "Would create 'alpha'" in out
        assert "Would update 'beta'" in out
        assert "Would skip 'gamma'" in out
        assert "Source configs" in out
        assert "Would be created" in out
        assert "Would be updated" in out
        assert "No changes were made" in out

    def test_empty_skip_lines_omits_blank_line(self, capsys):
        print_dry_run_preview(
            create_lines=["✓ Would create 'x'"],
            update_lines=[],
            skip_lines=[],
            source_count=1,
            target_count=0,
            would_create=1,
            would_update=0,
            skipped_total=0,
            skipped_detail="none",
            entity_name="dashboards",
        )
        out = capsys.readouterr().out
        # No skip section present
        assert "Would skip" in out  # summary line still present

    def test_counts_in_summary(self, capsys):
        print_dry_run_preview(
            create_lines=[],
            update_lines=[],
            skip_lines=[],
            source_count=10,
            target_count=5,
            would_create=3,
            would_update=2,
            skipped_total=5,
            skipped_detail="2 identical, 3 invalid",
            entity_name="alerts",
        )
        out = capsys.readouterr().out
        assert "10" in out  # source_count
        assert "5" in out   # target_count / would_update
        assert "3" in out   # would_create
        assert "2 identical, 3 invalid" in out
        # target after migration = 5 + 3 = 8
        assert "8" in out
