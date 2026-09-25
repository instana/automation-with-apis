"""Unit tests for the shared utils module."""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils import build_api, print_api_error, empty_result, partial_result, make_result
from instana_client.api.application_settings_api import ApplicationSettingsApi
from instana_client.api.application_alert_configuration_api import ApplicationAlertConfigurationApi
from instana_client.api.event_settings_api import EventSettingsApi
from instana_client.api.infrastructure_alert_configuration_api import InfrastructureAlertConfigurationApi
from instana_client.exceptions import ApiException


class TestUtils:
    """Test cases for utils.py helper functions."""

    def test_migration_result_helpers(self):
        """Test result helper functions."""
        assert empty_result() == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}
        assert partial_result(5) == {"source": 5, "migrated": 0, "updated": 0, "skipped": 0}
        assert make_result(10, 5, 2, 3) == {"source": 10, "migrated": 5, "updated": 2, "skipped": 3}

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
