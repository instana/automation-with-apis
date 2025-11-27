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
        
        assert configs == []

    def test_get_source_configs_file_not_found(self):
        """Test handling file not found error when getting source configs."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            configs = self.migrator._get_source_configs()
            
            assert configs == []

    def test_get_source_configs_invalid_json(self):
        """Test handling invalid JSON when getting source configs."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            configs = self.migrator._get_source_configs()
            
            assert configs == []

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
        
        assert configs == []

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
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {}}
        
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
            'eventFilteringConfiguration': {},
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

    @patch('migrator.requests.post')
    def test_create_config_failure(self, mock_post):
        """Test failed config creation."""
        config = {"alertName": "Test Config", "eventFilteringConfiguration": {}}
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_create_config_exception(self, mock_put):
        """Test config creation with exception."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {}}
        
        mock_put.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._create_config(config, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_config_success(self, mock_put):
        """Test successful config update."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {}}
        config_id = "existing_id"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "existing_id"}
        mock_put.return_value = mock_response
        
        result = self.migrator._update_config(config, config_id, "Test Config")
        
        assert result is True
        # The _format_config_for_api method adds additional fields
        expected_config = {
            'id': 'test_id',
            'alertName': 'Test Config',
            'eventFilteringConfiguration': {},
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
        config = {"alertName": "Test Config", "eventFilteringConfiguration": {}}
        config_id = "existing_id"
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_put.return_value = mock_response
        
        result = self.migrator._update_config(config, config_id, "Test Config")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_config_exception(self, mock_put):
        """Test config update with exception."""
        config = {"id": "test_id", "alertName": "Test Config", "eventFilteringConfiguration": {}}
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
        
        assert result == {"migrated": 2, "updated": 0, "skipped": 0}
        assert mock_create.call_count == 2

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    @patch.object(AlertConfigsMigrator, '_update_config')
    @patch.object(AlertConfigsMigrator, '_create_config')
    def test_migrate_with_duplicates(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with duplicate configs."""
        source_configs = [
            {"id": "config1_id", "alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"id": "config2_id", "alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id"}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "update"
        mock_update.return_value = True
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"migrated": 1, "updated": 1, "skipped": 0}
        mock_update.assert_called_once()

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    def test_migrate_skip_duplicates(self, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with skipped duplicates."""
        source_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id"}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "skip"
        
        with patch.object(self.migrator, '_create_config', return_value=True):
            result = self.migrator.migrate()
            
            assert result == {"migrated": 1, "updated": 0, "skipped": 1}

    @patch.object(AlertConfigsMigrator, '_get_source_configs')
    @patch.object(AlertConfigsMigrator, '_get_target_configs')
    @patch.object(AlertConfigsMigrator, '_prompt_for_duplicate_config')
    def test_migrate_cancel(self, mock_prompt, mock_get_target, mock_get_source):
        """Test migration cancellation."""
        source_configs = [
            {"alertName": "Config 1", "eventFilteringConfiguration": {}},
            {"alertName": "Config 2", "eventFilteringConfiguration": {}}
        ]
        target_configs = [{"alertName": "Config 1", "id": "existing_id"}]
        
        mock_get_source.return_value = source_configs
        mock_get_target.return_value = target_configs
        mock_prompt.return_value = "cancel"
        
        result = self.migrator.migrate()
        
        assert result == {"migrated": 0, "updated": 0, "skipped": 0}

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
                    
                    assert result == {"migrated": 1, "updated": 0, "skipped": 0}
