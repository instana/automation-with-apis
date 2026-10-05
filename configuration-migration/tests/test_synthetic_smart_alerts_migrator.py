"""Unit tests for the SyntheticSmartAlertsMigrator class."""

import pytest
import json
import requests
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
import importlib.util

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
_synth_alerts_dir = os.path.join(os.path.dirname(__file__), '..', 'synthetic-smart-alerts')
_spec = importlib.util.spec_from_file_location("migrator", os.path.join(_synth_alerts_dir, "migrator.py"))
migrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrator)
sys.modules['migrator'] = migrator
SyntheticSmartAlertsMigrator = migrator.SyntheticSmartAlertsMigrator
from config import Config
import utils


class TestSyntheticSmartAlertsMigrator:
    """Test cases for the SyntheticSmartAlertsMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        sys.modules['migrator'] = migrator
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_synthetic_smart_alerts.json"

        self.migrator = SyntheticSmartAlertsMigrator(self.config)
        self.migrator._get_channel_id_map = MagicMock(return_value={})

    def test_init(self):
        """Test migrator initialization."""
        assert self.migrator.config == self.config
        assert self.migrator.channel_id_map == {}
        assert self.migrator.synthetic_test_id_map == {}

    @patch('base_smart_alerts_migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        SyntheticSmartAlertsMigrator(self.config)
        mock_disable_warnings.assert_called_once()

    def test_get_source_configs_from_file(self):
        """Test getting source configs from JSON file."""
        test_configs = [
            {"name": "Synthetic Alert 1", "syntheticTestIds": ["test1"], "severity": 5},
            {"name": "Synthetic Alert 2", "syntheticTestIds": ["test2"], "severity": 10}
        ]

        with patch('builtins.open', mock_open(read_data=json.dumps(test_configs))):
            configs = self.migrator._get_source_configs()
            assert configs == test_configs

    def test_get_source_configs_from_file_error(self):
        """Test file read error handling when getting source configs."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            configs = self.migrator._get_source_configs()
            assert configs is None

    @patch('requests.get')
    def test_get_source_configs_from_api(self, mock_get):
        """Test getting source configs from Instana API."""
        self.config.events_source = "api"
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": "1", "name": "Synthetic Alert 1"}]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with patch('builtins.open', mock_open()):
            configs = self.migrator._get_source_configs()
            assert len(configs) == 1
            assert configs[0]["name"] == "Synthetic Alert 1"

    @patch('requests.get')
    def test_get_source_configs_from_api_exception(self, mock_get):
        """Test request exception handling when getting source configs."""
        self.config.events_source = "api"
        mock_get.side_effect = requests.RequestException("connection error")

        configs = self.migrator._get_source_configs()
        assert configs is None

    @patch('requests.get')
    def test_get_target_configs(self, mock_get):
        """Test getting target configs."""
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": "target-1", "name": "Synthetic Alert Target"}]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        configs = self.migrator._get_target_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "Synthetic Alert Target"

    @patch('requests.get')
    def test_get_target_configs_exception(self, mock_get):
        """Test request exception handling when getting target configs."""
        mock_get.side_effect = requests.RequestException("connection error")
        configs = self.migrator._get_target_configs()
        assert configs is None

    @patch('requests.post')
    def test_create_config_success(self, mock_post):
        """Test creating a synthetic smart alert configuration successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "created-1"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        config = {
            "name": "Synthetic Alert",
            "syntheticTestIds": [],
            "severity": 5
        }
        result = self.migrator._create_config(config, "Synthetic Alert")
        assert result is True

    @patch('requests.post')
    def test_create_config_failure(self, mock_post):
        """Test creating a synthetic smart alert configuration with API failure."""
        mock_post.side_effect = requests.RequestException("API Error")

        config = {
            "name": "Synthetic Alert",
            "syntheticTestIds": [],
            "severity": 5
        }
        result = self.migrator._create_config(config, "Synthetic Alert")
        assert result is False

    @patch('requests.post')
    def test_update_config_success(self, mock_post):
        """Test updating a synthetic smart alert configuration successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "target-1"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        config = {
            "name": "Synthetic Alert",
            "syntheticTestIds": [],
            "severity": 5
        }
        result = self.migrator._update_config(config, "target-1", "Synthetic Alert")
        assert result is True

    @patch('requests.post')
    def test_update_config_failure(self, mock_post):
        """Test updating a synthetic smart alert configuration with API failure."""
        mock_post.side_effect = requests.RequestException("API Error")

        config = {
            "name": "Synthetic Alert",
            "syntheticTestIds": [],
            "severity": 5
        }
        result = self.migrator._update_config(config, "target-1", "Synthetic Alert")
        assert result is False

    def test_format_config_for_api_remapping(self):
        """Test payload formatting and syntheticTestIds remapping."""
        self.migrator.synthetic_test_id_map = {"src-test-1": "tgt-test-1"}
        self.migrator._synthetic_test_map_fetched = True

        config = {
            "id": "old-id",
            "name": "Test Alert",
            "syntheticTestIds": ["src-test-1"],
            "alertChannelIds": [],
            "created": 123456,
            "threshold": {"lastUpdated": 9999, "type": "static"}
        }

        formatted = self.migrator._format_config_for_api(config, validate=True)
        assert "id" not in formatted
        assert "created" not in formatted
        assert formatted["syntheticTestIds"] == ["tgt-test-1"]
        assert "lastUpdated" not in formatted["threshold"]

    def test_format_config_unmapped_test_error(self):
        """Test error raised when synthetic test cannot be mapped."""
        self.migrator.synthetic_test_id_map = {}
        self.migrator.synthetic_test_name_map = {"src-test-1": "Ping Test"}
        self.migrator._synthetic_test_map_fetched = True

        config = {
            "name": "Test Alert",
            "syntheticTestIds": ["src-test-1"],
            "alertChannelIds": []
        }

        with pytest.raises(ValueError, match="synthetic test\\(s\\) 'Ping Test' not found in target"):
            self.migrator._format_config_for_api(config, validate=True)

    def test_format_config_file_mode_target_fallback(self):
        """Test fallback to target config's test IDs when source map not fetched."""
        self.migrator.synthetic_test_id_map = {}
        self.migrator._synthetic_test_map_fetched = False

        config = {
            "name": "Test Alert",
            "syntheticTestIds": ["src-test-1"],
            "alertChannelIds": []
        }
        target_config = {
            "id": "tgt-alert-1",
            "name": "Test Alert",
            "syntheticTestIds": ["tgt-test-1"]
        }

        formatted = self.migrator._format_config_for_api(config, validate=True, target_config=target_config)
        assert formatted["syntheticTestIds"] == ["tgt-test-1"]

    @patch('requests.get')
    def test_get_synthetic_test_id_map(self, mock_get):
        """Test building synthetic test ID map between source and target backends."""
        def mock_get_impl(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "source.com" in url:
                resp.json.return_value = [
                    {"id": "src-t1", "label": "HTTP Check"},
                    {"id": "src-t2", "label": "SSL Check"}
                ]
            else:
                resp.json.return_value = [
                    {"id": "tgt-t1", "label": "HTTP Check"},
                    {"id": "tgt-t2", "label": "SSL Check"}
                ]
            return resp

        mock_get.side_effect = mock_get_impl

        test_map = self.migrator._get_synthetic_test_id_map()
        assert test_map == {"src-t1": "tgt-t1", "src-t2": "tgt-t2"}
        assert self.migrator._synthetic_test_map_fetched is True
        assert self.migrator.synthetic_test_name_map["src-t1"] == "HTTP Check"
