"""Unit tests for the InfrastructureSmartAlertsMigrator class."""

import pytest
import json
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
import importlib.util
import urllib3

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
_infra_dir = os.path.join(os.path.dirname(__file__), '..', 'infrastructure-smart-alerts')
_spec = importlib.util.spec_from_file_location("migrator", os.path.join(_infra_dir, "migrator.py"))
migrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrator)
sys.modules['migrator'] = migrator
InfrastructureSmartAlertsMigrator = migrator.InfrastructureSmartAlertsMigrator
from config import Config
import utils
from instana_client.exceptions import ApiException
from instana_client.models.infra_alert_config import InfraAlertConfig


class TestInfrastructureSmartAlertsMigrator:
    """Test cases for the InfrastructureSmartAlertsMigrator class."""

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
        self.config.events_file_path = "test_infra_configs.json"

        self.migrator = InfrastructureSmartAlertsMigrator(self.config)
        self.migrator._get_channel_id_map = MagicMock(return_value={})

    def test_init(self):
        """Test migrator initialization."""
        assert self.migrator.config == self.config
        assert self.migrator.channel_id_map == {}

    @patch('base_smart_alerts_migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        InfrastructureSmartAlertsMigrator(self.config)
        mock_disable_warnings.assert_called_once()

    def test_get_source_configs_from_file(self):
        """Test getting source configs from JSON file."""
        test_configs = [
            {"name": "Infra Alert 1", "granularity": 60000, "description": "desc 1"},
            {"name": "Infra Alert 2", "granularity": 60000, "description": "desc 2"}
        ]

        with patch('builtins.open', mock_open(read_data=json.dumps(test_configs))):
            configs = self.migrator._get_source_configs()
            assert configs == test_configs

    def test_get_source_configs_from_file_error(self):
        """Test file read error handling when getting source configs."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            configs = self.migrator._get_source_configs()
            assert configs is None

    @patch('base_smart_alerts_migrator.build_api')
    def test_get_source_configs_from_api(self, mock_build_client):
        """Test getting source configs from Instana API."""
        self.config.events_source = "api"
        mock_api = MagicMock()
        mock_item = MagicMock()
        mock_item.to_dict.return_value = {"id": "1", "name": "Infra Alert 1"}
        mock_api.find_active_infra_alert_configs.return_value = [mock_item]
        mock_build_client.return_value = mock_api

        configs = self.migrator._get_source_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "Infra Alert 1"

    @patch('base_smart_alerts_migrator.build_api')
    def test_get_source_configs_from_api_exception(self, mock_build_client):
        """Test API exception handling when getting source configs."""
        self.config.events_source = "api"
        mock_api = MagicMock()
        mock_api.find_active_infra_alert_configs.side_effect = ApiException(status=500, reason="Server Error")
        mock_build_client.return_value = mock_api

        configs = self.migrator._get_source_configs()
        assert configs is None

    @patch('base_smart_alerts_migrator.build_api')
    def test_get_target_configs(self, mock_build_client):
        """Test getting target configs."""
        mock_api = MagicMock()
        mock_item = MagicMock()
        mock_item.to_dict.return_value = {"id": "target-1", "name": "Infra Alert Target"}
        mock_api.find_active_infra_alert_configs.return_value = [mock_item]
        mock_build_client.return_value = mock_api

        configs = self.migrator._get_target_configs()
        assert len(configs) == 1
        assert configs[0]["id"] == "target-1"

    @patch('base_smart_alerts_migrator.build_api')
    def test_get_target_configs_exception(self, mock_build_client):
        """Test API exception handling when getting target configs."""
        mock_api = MagicMock()
        mock_api.find_active_infra_alert_configs.side_effect = ApiException(status=500, reason="Server Error")
        mock_build_client.return_value = mock_api

        configs = self.migrator._get_target_configs()
        assert configs is None

    def test_format_config_for_api_strips_metadata(self):
        """Test that read-only / metadata fields are stripped."""
        config = {
            "id": "src-123",
            "name": "Host CPU high",
            "description": "CPU Alert",
            "created": 1700000000,
            "initialCreated": 1700000000,
            "lastUpdated": 1700000000,
            "invalid": False,
            "readOnly": False,
            "enabled": True,
            "alertChannelNames": ["Slack #alerts"],
            "alertChannelIds": ["c1", "c2"],
            "granularity": 60000,
        }
        self.migrator.channel_id_map = {"c1": "target-c1", "c2": "target-c2"}
        self.migrator._channel_map_fetched = True

        formatted = self.migrator._format_config_for_api(config)

        assert "id" not in formatted
        assert "created" not in formatted
        assert "initialCreated" not in formatted
        assert "lastUpdated" not in formatted
        assert "readOnly" not in formatted
        assert "enabled" not in formatted
        assert "alertChannelNames" not in formatted
        assert formatted["name"] == "Host CPU high"
        assert formatted["alertChannelIds"] == ["target-c1", "target-c2"]
        assert formatted["customPayloadFields"] == []
        assert formatted["groupBy"] == []

    def test_format_config_for_api_missing_name(self):
        """Test validation error when name is missing."""
        config = {"granularity": 60000}
        with pytest.raises(ValueError, match="must have a 'name' field"):
            self.migrator._format_config_for_api(config)

    def test_format_config_alert_channels_dict_remapping(self):
        """Test severity-based alertChannels dict remapping."""
        config = {
            "name": "Infra Alert",
            "alertChannels": {
                "5": ["c1"],
                "10": ["c2"]
            }
        }
        self.migrator.channel_id_map = {"c1": "tgt-c1", "c2": "tgt-c2"}
        self.migrator._channel_map_fetched = True

        formatted = self.migrator._format_config_for_api(config)
        assert formatted["alertChannels"] == {"5": ["tgt-c1"], "10": ["tgt-c2"]}

    def test_configs_are_equal(self):
        """Test equality check ignores IDs and metadata."""
        src = {
            "id": "src-1",
            "name": "Alert 1",
            "description": "Desc",
            "granularity": 60000,
            "created": 100,
            "alertChannelIds": ["ch-1"]
        }
        tgt = {
            "id": "tgt-1",
            "name": "Alert 1",
            "description": "Desc",
            "granularity": 60000,
            "created": 200,
            "alertChannelIds": ["tgt-ch-1"]
        }
        assert self.migrator._configs_are_equal(src, tgt) is True

        different_tgt = {
            "id": "tgt-1",
            "name": "Alert 1",
            "description": "Different Desc",
            "granularity": 60000,
        }
        assert self.migrator._configs_are_equal(src, different_tgt) is False

    @patch.object(InfraAlertConfig, 'from_dict')
    @patch('base_smart_alerts_migrator.build_api')
    def test_create_config_success(self, mock_build_client, mock_from_dict):
        """Test successful creation of an infra alert configuration."""
        mock_api = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "new-id"
        mock_api.create_infra_alert_config.return_value = mock_result
        mock_build_client.return_value = mock_api

        config = {"name": "New Alert", "granularity": 60000}
        res = self.migrator._create_config(config, "New Alert")
        assert res is True
        mock_api.create_infra_alert_config.assert_called_once()

    @patch.object(InfraAlertConfig, 'from_dict')
    @patch('base_smart_alerts_migrator.build_api')
    def test_create_config_api_exception(self, mock_build_client, mock_from_dict):
        """Test API failure when creating an infra alert configuration."""
        mock_api = MagicMock()
        mock_api.create_infra_alert_config.side_effect = ApiException(status=400, reason="Bad Request")
        mock_build_client.return_value = mock_api

        config = {"name": "New Alert", "granularity": 60000}
        res = self.migrator._create_config(config, "New Alert")
        assert res is False

    @patch.object(InfraAlertConfig, 'from_dict')
    @patch('base_smart_alerts_migrator.build_api')
    def test_update_config_success(self, mock_build_client, mock_from_dict):
        """Test successful update of an infra alert configuration."""
        mock_api = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "target-id"
        mock_api.update_infra_alert_config.return_value = mock_result
        mock_build_client.return_value = mock_api

        config = {"name": "Existing Alert", "granularity": 60000}
        res = self.migrator._update_config(config, "target-id", "Existing Alert")
        assert res is True
        mock_api.update_infra_alert_config.assert_called_once()

    @patch('requests.get')
    def test_get_channel_id_map(self, mock_get):
        """Test building channel ID map."""
        self.migrator._get_channel_id_map = lambda: InfrastructureSmartAlertsMigrator._get_channel_id_map(self.migrator)
        self.config.events_source = "api"
        source_resp = MagicMock()
        source_resp.status_code = 200
        source_resp.json.return_value = [{"id": "s1", "name": "Channel A"}]

        target_resp = MagicMock()
        target_resp.status_code = 200
        target_resp.json.return_value = [{"id": "t1", "name": "Channel A"}]

        mock_get.side_effect = [source_resp, target_resp]

        channel_map = self.migrator._get_channel_id_map()
        assert channel_map == {"s1": "t1"}
        assert self.migrator._channel_map_fetched is True

    @patch('builtins.input', return_value='s')
    def test_prompt_for_duplicate_config_skip(self, mock_input):
        """Test duplicate prompt returns skip."""
        res = self.migrator._prompt_for_duplicate_config("Test Alert")
        assert res == 'skip'

    @patch('builtins.input', return_value='u')
    def test_prompt_for_duplicate_config_update(self, mock_input):
        """Test duplicate prompt returns update."""
        res = self.migrator._prompt_for_duplicate_config("Test Alert")
        assert res == 'update'

    @patch('builtins.input', return_value='c')
    def test_prompt_for_duplicate_config_cancel(self, mock_input):
        """Test duplicate prompt returns cancel."""
        res = self.migrator._prompt_for_duplicate_config("Test Alert")
        assert res == 'cancel'

    def test_migrate_full_flow(self):
        """Test full migration orchestration."""
        self.migrator._get_source_configs = MagicMock(return_value=[
            {"id": "s1", "name": "Alert 1", "description": "desc1"},
            {"id": "s2", "name": "Alert 2", "description": "desc2"},
        ])
        self.migrator._get_target_configs = MagicMock(return_value=[
            {"id": "t1", "name": "Alert 1", "description": "desc1"}, # Identical
        ])
        self.migrator._create_config = MagicMock(return_value=True)

        res = self.migrator.migrate()
        assert res["source"] == 2
        assert res["migrated"] == 1
        assert res["skipped_identical"] == 1
        assert res["updated"] == 0
        assert res["failed"] == 0
