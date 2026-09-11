"""Unit tests for the AlertConfigsMigrator class."""

import pytest
import json
import requests
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'alert-configs'))
from migrator import AlertConfigsMigrator
from config import Config


class TestAlertConfigsMigrator:
    """Test cases for the AlertConfigsMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_configs.json"
        
        self.migrator = AlertConfigsMigrator(self.config)
        # Mock mapping calls to prevent network hits for other tests
        self.migrator._get_channel_id_map = MagicMock(return_value={})
        self.migrator._get_event_id_map = MagicMock(return_value={})

    def test_init(self):
        """Test migrator initialization."""
        assert self.migrator.config == self.config
        assert self.migrator.req_alert_configs == "/api/events/settings/alerts"

    @patch('migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        migrator = AlertConfigsMigrator(self.config)
        
        mock_disable_warnings.assert_called_once()

    def test_get_source_configs_from_file(self):
        """Test getting source configs from file."""
        test_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(test_configs))):
            configs = self.migrator._get_source_configs()
            
            assert configs == test_configs

    @patch('migrator.requests.get')
    def test_get_source_configs_from_api(self, mock_get):
        """Test getting source configs from API."""
        self.config.events_source = "api"
        test_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_configs
        mock_get.return_value = mock_response
        
        configs = self.migrator._get_source_configs()
        
        assert configs == test_configs
        mock_get.assert_called_once_with(
            f"{self.config.source_url}{self.migrator.req_alert_configs}",
            headers=self.config.get_source_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_source_configs_api_error(self, mock_get):
        """Test handling API error when getting source configs."""
        self.config.events_source = "api"
        
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        configs = self.migrator._get_source_configs()

        assert configs is None

    def test_get_source_configs_file_not_found(self):
        """Test handling file not found error when getting source configs."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            configs = self.migrator._get_source_configs()

            assert configs is None

    def test_get_source_configs_invalid_json(self):
        """Test handling invalid JSON when getting source configs."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            configs = self.migrator._get_source_configs()

            assert configs is None

    @patch('migrator.requests.get')
    def test_get_target_configs(self, mock_get):
        """Test getting target configs."""
        test_configs = [
            {"alertName": "Existing Config 1", "id": "1"},
            {"alertName": "Existing Config 2", "id": "2"}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_configs
        mock_get.return_value = mock_response
        
        configs = self.migrator._get_target_configs()
        
        assert configs == test_configs
        mock_get.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_configs}",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_target_configs_error(self, mock_get):
        """Test handling error when getting target configs."""
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        configs = self.migrator._get_target_configs()

        assert configs is None

    @patch('builtins.input', return_value='s')
    def test_prompt_for_duplicate_config_skip(self, mock_input):
        """Test prompting for duplicate config - skip choice."""
        choice = self.migrator._prompt_for_duplicate_config("Test Config")
        
        assert choice == "skip"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='u')
    def test_prompt_for_duplicate_config_update(self, mock_input):
        """Test prompting for duplicate config - update choice."""
        choice = self.migrator._prompt_for_duplicate_config("Test Config")
        
        assert choice == "update"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='c')
    def test_prompt_for_duplicate_config_cancel(self, mock_input):
        """Test prompting for duplicate config - cancel choice."""
        choice = self.migrator._prompt_for_duplicate_config("Test Config")
        
        assert choice == "cancel"
        mock_input.assert_called_once()

    @patch('builtins.input', side_effect=['invalid', 's'])
    def test_prompt_for_duplicate_config_invalid_then_valid(self, mock_input):
        """Test prompting for duplicate config - invalid input then valid."""
        choice = self.migrator._prompt_for_duplicate_config("Test Config")
        
        assert choice == "skip"
        assert mock_input.call_count == 2

    @patch('migrator.requests.put')
    def test_create_config_success(self, mock_put):
        """Test successful config creation."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "test_id"}
        mock_put.return_value = mock_response
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is True
        # The _format_config_for_api method adds additional fields
        expected_config = {
            'id': 'test_id',
            'alertName': 'Test Config',
            'eventFilteringConfiguration': {
                'eventTypes': ['INCIDENT'],
                'validVersion': 1,
                'query': None,
            },
            'customPayloadFields': [],
            'integrationIds': [],
            'muteUntil': 0,
            'includeEntityNameInLegacyAlerts': False
        }
        mock_put.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_configs}/test_id",
            json=expected_config,
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.put')
    def test_create_config_failure(self, mock_put):
        """Test failed config creation."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
        mock_put.return_value = mock_response
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    @patch('migrator.uuid.uuid4')
    def test_create_config_generates_uuid_when_no_id(self, mock_uuid4, mock_put):
        """Test that a UUID is generated when source config has no id."""
        mock_uuid4.return_value = MagicMock(__str__=lambda self: "generated-uuid")
        config = {"alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "generated-uuid"}
        mock_put.return_value = mock_response
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is True
        call_url = mock_put.call_args[0][0]
        assert call_url.endswith("/generated-uuid")
        assert mock_put.call_args[1]['json']['id'] == "generated-uuid"

    @patch('migrator.requests.put')
    def test_create_config_exception(self, mock_put):
        """Test config creation with exception."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        
        mock_put.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_config_success(self, mock_put):
        """Test successful config update."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        config_id = "existing_id"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "existing_id"}
        mock_put.return_value = mock_response
        
        result = self.migrator._update_config(config, config_id, "Test Config")
        
        assert result is True
        # The _format_config_for_api method adds additional fields
        expected_config = {
            'id': 'existing_id',
            'alertName': 'Test Config',
            'eventFilteringConfiguration': {
                'eventTypes': ['INCIDENT'],
                'validVersion': 1,
                'query': None,
            },
            'customPayloadFields': [],
            'integrationIds': [],
            'muteUntil': 0,
            'includeEntityNameInLegacyAlerts': False
        }
        mock_put.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_configs}/existing_id",
            json=expected_config,
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.put')
    def test_update_config_failure(self, mock_put):
        """Test failed config update."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        config_id = "existing_id"
        
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
        mock_put.return_value = mock_response
        
        result = self.migrator._update_config(config, config_id, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_config_exception(self, mock_put):
        """Test config update with exception."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        config_id = "existing_id"
        
        mock_put.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._update_config(config, config_id, "Test Config")
        
        assert result is False

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    @patch.object(AlertConfigsMigrator, '_create_config')
    def test_migrate_success(self, mock_create, mock_prompt, mock_get_target, mock_get_source):
        """Test successful migration."""
        source_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        target_configs = []
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 2, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}
        assert mock_create.call_count == 2

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    @patch.object(AlertConfigsMigrator, '_update_config')
    @patch.object(AlertConfigsMigrator, '_create_config')
    def test_migrate_with_duplicates(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with duplicate configs."""
        source_configs = [
            {"id": "config1_id", "alertName": "Config 1", "eventFilteringConfiguration": {"eventTypes": ["incident"]}},
            {"id": "config2_id", "alertName": "Config 2", "eventFilteringConfiguration": {"eventTypes": ["warning"]}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id", "eventFilteringConfiguration": {"eventTypes": ["critical"]}}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "update"
        mock_update.return_value = True
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 1, "updated": 1, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}
        mock_update.assert_called_once()

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    def test_migrate_skip_duplicates(self, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with skipped duplicates."""
        source_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {"eventTypes": ["incident"]}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {"eventTypes": ["warning"]}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id", "eventFilteringConfiguration": {"eventTypes": ["critical"]}}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "skip"
        
        with patch.object(self.migrator, '_create_config', return_value=True):
            result = self.migrator.migrate()
            
            assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped_identical": 0, "skipped_user": 1, "skipped_invalid": 0, "failed": 0}

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    def test_migrate_cancel(self, mock_prompt, mock_get_target, mock_get_source):
        """Test migration cancellation."""
        source_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {"eventTypes": ["incident"]}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {"eventTypes": ["warning"]}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id", "eventFilteringConfiguration": {"eventTypes": ["critical"]}}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "cancel"
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

    def test_migrate_skip_config_without_name(self):
        """Test that configs without alertName are skipped."""
        source_configs = [
            {"eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        target_configs = []
        
        with patch.object(self.migrator, '_get_source_configs', return_value=source_configs):
            with patch.object(self.migrator, '_get_target_configs', return_value=target_configs):
                with patch.object(self.migrator, '_create_config', return_value=True):
                    result = self.migrator.migrate()
                    
                    assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

    def test_configs_are_equal(self):
        """Test checking if source and target configs are content-equal."""
        efc = {"eventTypes": ["INCIDENT"]}
        source = {"id": "src_id", "alertName": "Alert 1", "muteUntil": 0, "eventFilteringConfiguration": efc}
        target = {"id": "tgt_id", "alertName": "Alert 1", "muteUntil": 0, "lastUpdated": 12345, "eventFilteringConfiguration": efc}
        assert self.migrator._configs_are_equal(source, target) is True

        # muteUntil difference should still be detected
        different = {"id": "tgt_id", "alertName": "Alert 1", "muteUntil": 3600, "eventFilteringConfiguration": efc}
        assert self.migrator._configs_are_equal(source, different) is False

        # integrationIds differences are ignored (cross-system IDs)
        source_with_channel = {**source, "integrationIds": ["src_channel_id"]}
        target_with_channel = {**target, "integrationIds": ["tgt_channel_id"]}
        assert self.migrator._configs_are_equal(source_with_channel, target_with_channel) is True

        # ruleIds differences inside eventFilteringConfiguration are also ignored
        source_with_rules = {**source, "eventFilteringConfiguration": {**efc, "ruleIds": ["src_rule_id"]}}
        target_with_rules = {**target, "eventFilteringConfiguration": {**efc, "ruleIds": ["tgt_rule_id"]}}
        assert self.migrator._configs_are_equal(source_with_rules, target_with_rules) is True

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_create_config')
    def test_migrate_auto_skips_identical(self, mock_create, mock_get_target, mock_get_source):
        """Test migrating automatically skips identical duplicates without prompt."""
        efc = {"eventTypes": ["INCIDENT"]}
        source_configs = [
            {"id": "src_id1", "alertName": "Config 1", "muteUntil": 0, "eventFilteringConfiguration": efc},
            {"id": "src_id2", "alertName": "Config 2", "muteUntil": 0, "eventFilteringConfiguration": efc}
        ]
        target_configs = [
            {"id": "tgt_id1", "alertName": "Config 1", "muteUntil": 0, "eventFilteringConfiguration": efc}
        ]
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_create.return_value = True

        result = self.migrator.migrate()

        # Config 1 is identical (should auto-skip)
        # Config 2 is new (should migrate)
        assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped_identical": 1, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}
        mock_create.assert_called_once_with(source_configs[1], "Config 2")

    @patch('migrator.requests.get')
    def test_dynamic_id_remapping(self, mock_get):
        """Test that ruleIds and integrationIds are correctly remapped dynamically."""
        # Restore real methods for this specific test
        self.migrator._get_channel_id_map = lambda: AlertConfigsMigrator._get_channel_id_map(self.migrator)
        self.migrator._get_event_id_map = lambda: AlertConfigsMigrator._get_event_id_map(self.migrator)

        # Setup mocks
        m_src_chan = MagicMock(status_code=200)
        m_src_chan.json.return_value = [{"name": "Slack Channel", "id": "src_channel_id"}]
        
        m_tgt_chan = MagicMock(status_code=200)
        m_tgt_chan.json.return_value = [{"name": "Slack Channel", "id": "tgt_channel_id"}]
        
        m_src_evt = MagicMock(status_code=200)
        m_src_evt.json.return_value = [{"name": "Custom Error", "id": "src_event_id"}]
        
        m_tgt_evt = MagicMock(status_code=200)
        m_tgt_evt.json.return_value = [{"name": "Custom Error", "id": "tgt_event_id"}]
        
        mock_get.side_effect = [
            m_src_chan,
            m_tgt_chan,
            m_src_evt,
            m_tgt_evt
        ]
        
        # Populate channel and event maps
        self.migrator.channel_id_map = self.migrator._get_channel_id_map()
        self.migrator.event_id_map = self.migrator._get_event_id_map()
        
        assert self.migrator.channel_id_map == {"src_channel_id": "tgt_channel_id"}
        assert self.migrator.event_id_map == {"src_event_id": "tgt_event_id"}
        
        # Test formatting
        config = {
            "id": "alert_id",
            "alertName": "Test Alert",
            "integrationIds": ["src_channel_id", "unmapped_channel_id"],
            "eventFilteringConfiguration": {
                "ruleIds": ["src_event_id", "unmapped_event_id"]
            }
        }
        
        formatted = self.migrator._format_config_for_api(config)
        
        assert formatted["integrationIds"] == ["tgt_channel_id"]
        # unmapped_event_id has no match in the event map — it is passed through as-is
        assert formatted["eventFilteringConfiguration"]["ruleIds"] == ["tgt_event_id", "unmapped_event_id"]

    def test_format_config_raises_when_no_filter_selectors(self):
        """Validation rejects configs where all four filter fields are empty/absent."""
        config = {
            "alertName": "Empty Filter",
            "eventFilteringConfiguration": {
                "query": None,
                "ruleIds": [],
                "eventTypes": [],
                "applicationAlertConfigIds": []
            }
        }
        with pytest.raises(ValueError, match="at least one must be set"):
            self.migrator._format_config_for_api(config)

    def test_format_config_accepts_query_only_filter(self):
        """query-only configs are rejected — the target API requires a non-empty
        eventTypes, ruleIds, or applicationAlertConfigIds alongside query."""
        config = {
            "alertName": "Query Filter",
            "eventFilteringConfiguration": {
                "query": "entity.type:host",
                "ruleIds": [],
                "eventTypes": [],
                "applicationAlertConfigIds": []
            }
        }
        with pytest.raises(ValueError, match="no ruleIds, eventTypes"):
            self.migrator._format_config_for_api(config)

    def test_format_config_skips_validation_when_disabled(self):
        """validate=False must not raise even when all filter fields are empty."""
        config = {
            "alertName": "Empty Filter",
            "eventFilteringConfiguration": {
                "query": None,
                "ruleIds": [],
                "eventTypes": [],
                "applicationAlertConfigIds": []
            }
        }
        # Should not raise
        result = self.migrator._format_config_for_api(config, validate=False)
        assert result["alertName"] == "Empty Filter"

    def test_format_config_warns_on_unmatched_integration_ids(self, capsys):
        """Warning is printed for integrationIds not found in the channel map."""
        self.migrator._channel_map_fetched = True
        self.migrator.channel_id_map = {}  # fetched but empty → no matches
        config = {
            "alertName": "Alert",
            "integrationIds": ["unknown_channel_id"],
            "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}
        }
        result = self.migrator._format_config_for_api(config)
        assert result["integrationIds"] == []
        captured = capsys.readouterr()
        assert "integrationId(s) not found" in captured.out

    def test_format_config_warns_on_unmatched_rule_ids(self, capsys):
        """Warning is printed for ruleIds not found in the event map."""
        self.migrator._event_map_fetched = True
        self.migrator.event_id_map = {}  # fetched but empty → no matches
        config = {
            "alertName": "Alert",
            "eventFilteringConfiguration": {
                "ruleIds": ["unknown_rule_id"],
                "eventTypes": ["INCIDENT"]
            }
        }
        result = self.migrator._format_config_for_api(config)
        # Unmatched ruleIds are passed through as-is (original source ID preserved)
        assert result["eventFilteringConfiguration"]["ruleIds"] == ["unknown_rule_id"]
        captured = capsys.readouterr()
        assert "ruleId(s) not found" in captured.out

    def test_format_config_passthrough_when_map_not_fetched(self):
        """IDs are passed through unchanged when the channel/event map was never fetched."""
        # Default state: _channel_map_fetched=False, _event_map_fetched=False
        config = {
            "alertName": "Alert",
            "integrationIds": ["some_channel_id"],
            "eventFilteringConfiguration": {
                "ruleIds": ["some_rule_id"],
                "eventTypes": ["INCIDENT"]
            }
        }
        result = self.migrator._format_config_for_api(config)
        assert result["integrationIds"] == ["some_channel_id"]
        assert result["eventFilteringConfiguration"]["ruleIds"] == ["some_rule_id"]

    def test_create_config_skips_on_empty_filter(self):
        """_create_config returns None (without HTTP call) when filter is empty."""
        config = {
            "alertName": "Bad Config",
            "eventFilteringConfiguration": {}
        }
        with patch('migrator.requests.put') as mock_put:
            result = self.migrator._create_config(config, "Bad Config")
        assert result is None
        mock_put.assert_not_called()

    def test_update_config_skips_on_empty_filter(self):
        """_update_config returns None (without HTTP call) when filter is empty."""
        config = {
            "alertName": "Bad Config",
            "eventFilteringConfiguration": {}
        }
        with patch('migrator.requests.put') as mock_put:
            result = self.migrator._update_config(config, "existing_id", "Bad Config")
        assert result is None
        mock_put.assert_not_called()

    def test_update_config_uses_target_id_in_body(self):
        """PUT body must contain target_id, not the source id (bug fix validation)."""
        config = {
            "id": "source_system_id",
            "alertName": "Test Config",
            "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}
        }
        target_id = "target_system_id"

        with patch('migrator.requests.put') as mock_put:
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": target_id}
            mock_put.return_value = mock_response

            result = self.migrator._update_config(config, target_id, "Test Config")

        assert result is True
        sent_body = mock_put.call_args[1]['json']
        assert sent_body['id'] == target_id, "PUT body must carry target_id, not source id"
        call_url = mock_put.call_args[0][0]
        assert call_url.endswith(f"/{target_id}")

    def test_configs_are_equal_eventTypes_order_insensitive(self):
        """Different ordering of eventTypes must not trigger a false mismatch."""
        efc_src = {"eventTypes": ["warning", "critical"]}
        efc_tgt = {"eventTypes": ["critical", "warning"]}
        source = {"alertName": "Alert", "muteUntil": 0, "eventFilteringConfiguration": efc_src}
        target = {"alertName": "Alert", "muteUntil": 0, "eventFilteringConfiguration": efc_tgt}
        assert self.migrator._configs_are_equal(source, target) is True

    def test_configs_are_equal_excludes_server_only_fields(self):
        """lastUpdated, invalid, alertChannelNames, applicationNames must be ignored."""
        efc = {"eventTypes": ["INCIDENT"]}
        source = {"alertName": "Alert", "muteUntil": 0, "eventFilteringConfiguration": efc}
        target = {
            "alertName": "Alert", "muteUntil": 0, "eventFilteringConfiguration": efc,
            "lastUpdated": 9999999, "invalid": True,
            "alertChannelNames": ["Slack"], "applicationNames": ["MyApp"]
        }
        assert self.migrator._configs_are_equal(source, target) is True

    def test_configs_are_equal_missing_alert_name_returns_false(self):
        """Missing alertName raises ValueError internally; _configs_are_equal must return False."""
        source = {"muteUntil": 0, "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        target = {"muteUntil": 0, "eventFilteringConfiguration": {"eventTypes": ["INCIDENT"]}}
        assert self.migrator._configs_are_equal(source, target) is False

    @patch.object(AlertConfigsMigrator, '_get_source_configs', return_value=None)
    def test_migrate_returns_zeros_when_source_fails(self, _mock):
        """migrate returns zero-filled dict when source fetch fails."""
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs', return_value=None)
    def test_migrate_returns_zeros_when_target_fails(self, _mock_tgt, mock_src):
        """migrate returns zero-filled dict (with source count) when target fetch fails."""
        mock_src.return_value = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        result = self.migrator.migrate()
        assert result == {"source": 2, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_create_config', return_value=False)
    def test_migrate_increments_failed_on_create_failure(self, _mock_create, mock_tgt, mock_src):
        """Failed _create_config calls must increment failed_count."""
        mock_src.return_value = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
        ]
        mock_tgt.return_value = []
        result = self.migrator.migrate()
        assert result["failed"] == 1
        assert result["migrated"] == 0

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config', return_value='update')
    @patch.object(AlertConfigsMigrator, '_update_config', return_value=False)
    def test_migrate_increments_failed_on_update_failure(self, _mock_upd, _mock_prompt, mock_tgt, mock_src):
        """Failed _update_config calls must increment failed_count."""
        efc = {"eventTypes": ["INCIDENT"]}
        mock_src.return_value = [{"alertName": "Config 1", "muteUntil": 0, "eventFilteringConfiguration": efc}]
        # Different muteUntil so equality check fails and we reach the prompt
        mock_tgt.return_value = [{"id": "tgt1", "alertName": "Config 1", "muteUntil": 3600, "eventFilteringConfiguration": efc}]
        result = self.migrator.migrate()
        assert result["failed"] == 1
        assert result["updated"] == 0

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    @patch.object(AlertConfigsMigrator, '_create_config')
    def test_migrate_matches_by_id_first(self, mock_create, mock_prompt, mock_tgt, mock_src):
        """A source config whose ID exists in the target is matched by ID, not name."""
        efc = {"eventTypes": ["INCIDENT"]}
        source_configs = [
            {"id": "shared_id", "alertName": "Config A", "muteUntil": 0, "eventFilteringConfiguration": efc},
        ]
        # Target has same ID but a different name — should still be found by ID
        target_configs = [
            {"id": "shared_id", "alertName": "Config B", "muteUntil": 0, "eventFilteringConfiguration": efc},
        ]
        mock_src.return_value = source_configs
        mock_tgt.return_value = target_configs
        mock_prompt.return_value = "skip"

        result = self.migrator.migrate()

        # Matched by ID → duplicate handling triggered (skipped_user), not a new create
        assert result["skipped_user"] == 1
        mock_create.assert_not_called()

    @patch('migrator.requests.get', side_effect=Exception("network failure"))
    def test_get_channel_id_map_returns_empty_on_exception(self, _mock):
        """Exception during channel map fetch returns empty dict and prints warning."""
        self.migrator._get_channel_id_map = lambda: AlertConfigsMigrator._get_channel_id_map(self.migrator)
        result = self.migrator._get_channel_id_map()
        assert result == {}
        assert self.migrator._channel_map_fetched is False

    @patch('migrator.requests.get', side_effect=Exception("network failure"))
    def test_get_event_id_map_returns_empty_on_exception(self, _mock):
        """Exception during event map fetch returns empty dict and prints warning."""
        self.migrator._get_event_id_map = lambda: AlertConfigsMigrator._get_event_id_map(self.migrator)
        result = self.migrator._get_event_id_map()
        assert result == {}
        assert self.migrator._event_map_fetched is False
