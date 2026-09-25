"""Unit tests for the BaseSmartAlertsMigrator class."""

import pytest
import json
from unittest.mock import patch, mock_open, MagicMock
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from base_smart_alerts_migrator import BaseSmartAlertsMigrator
from config import Config


class DummySmartAlertsMigrator(BaseSmartAlertsMigrator):
    entity_type_name = "dummy alert"

    def _fetch_source_configs_from_api(self):
        return []

    def _get_target_configs(self):
        return []

    def _create_config(self, config, config_name):
        return True

    def _update_config(self, config, target_id, config_name):
        return True

    def _format_config_for_api(self, config, validate=True):
        formatted = dict(config)
        self._strip_common_metadata(formatted)
        self._remap_alert_channels(formatted, validate=validate)
        return formatted


class TestBaseSmartAlertsMigrator:
    def setup_method(self):
        self.config = Config()
        self.config.source_token = "src-token"
        self.config.source_url = "https://source.example.com"
        self.config.target_token = "tgt-token"
        self.config.target_url = "https://target.example.com"
        self.config.verify_ssl = True
        self.config.events_source = "api"
        self.migrator = DummySmartAlertsMigrator(self.config)

    @patch('base_smart_alerts_migrator.urllib3.disable_warnings')
    def test_init_ssl_disabled(self, mock_disable):
        self.config.verify_ssl = False
        DummySmartAlertsMigrator(self.config)
        mock_disable.assert_called_once()

    def test_coerce_tag_filter_values(self):
        obj = {
            "type": "TAG_FILTER",
            "name": "agent.tag",
            "value": 1234,
            "nested": [{"type": "TAG_FILTER", "value": 56.78}]
        }
        res = self.migrator._coerce_tag_filter_values(obj)
        assert res["value"] == "1234"
        assert res["nested"][0]["value"] == "56.78"

    def test_strip_common_metadata(self):
        obj = {
            "id": "1",
            "created": 100,
            "initialCreated": 100,
            "lastUpdated": 100,
            "invalid": False,
            "readOnly": True,
            "enabled": True,
            "alertChannelNames": ["ch1"],
            "name": "Alert"
        }
        self.migrator._strip_common_metadata(obj)
        assert "id" not in obj
        assert "created" not in obj
        assert "lastUpdated" not in obj
        assert "readOnly" not in obj
        assert "enabled" not in obj
        assert obj["name"] == "Alert"

    def test_remap_alert_channels(self):
        self.migrator.channel_id_map = {"s1": "t1"}
        self.migrator._channel_map_fetched = True
        formatted = {
            "name": "Alert",
            "alertChannelIds": ["s1", "unknown"],
            "alertChannels": {"5": ["s1"]}
        }
        self.migrator._remap_alert_channels(formatted, validate=True)
        assert formatted["alertChannelIds"] == ["t1"]
        assert formatted["alertChannels"] == {"5": ["t1"]}

    def test_configs_are_equal(self):
        c1 = {"name": "Alert", "id": "1", "created": 100}
        c2 = {"name": "Alert", "id": "2", "created": 200}
        assert self.migrator._configs_are_equal(c1, c2) is True

        c3 = {"name": "Alert 2", "id": "2"}
        assert self.migrator._configs_are_equal(c1, c3) is False

    @patch('builtins.input', side_effect=['s', 'u', 'c'])
    def test_prompt_for_duplicate_config(self, mock_input):
        assert self.migrator._prompt_for_duplicate_config("alert1") == 'skip'
        assert self.migrator._prompt_for_duplicate_config("alert2") == 'update'
        assert self.migrator._prompt_for_duplicate_config("alert3") == 'cancel'

    def test_migrate_orchestration(self):
        self.migrator._get_source_configs = MagicMock(return_value=[
            {"id": "1", "name": "A1"},
            {"id": "2", "name": "A2"}
        ])
        self.migrator._get_target_configs = MagicMock(return_value=[
            {"id": "t1", "name": "A1"}
        ])
        self.migrator._get_channel_id_map = MagicMock(return_value={})

        res = self.migrator.migrate()
        assert res["source"] == 2
        assert res["migrated"] == 1
        assert res["skipped_identical"] == 1
