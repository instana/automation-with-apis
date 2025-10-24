"""Unit tests for the AlertChannelsMigrator class."""

import pytest
import json
import requests
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'alert-channels'))
from migrator import AlertChannelsMigrator
from config import Config


class TestAlertChannelsMigrator:
    """Test cases for the AlertChannelsMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_channels.json"
        
        self.migrator = AlertChannelsMigrator(self.config)

    def test_init(self):
        """Test migrator initialization."""
        assert self.migrator.config == self.config
        assert self.migrator.req_alert_channels == "/api/events/settings/alertingChannels"

    @patch('migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        migrator = AlertChannelsMigrator(self.config)
        
        mock_disable_warnings.assert_called_once()

    def test_get_source_channels_from_file(self):
        """Test getting source channels from file."""
        test_channels = [
            {"name": "Channel 1", "type": "email"},
            {"name": "Channel 2", "type": "slack"}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(test_channels))):
            channels = self.migrator._get_source_channels()
            
            assert channels == test_channels

    @patch('migrator.requests.get')
    def test_get_source_channels_from_api(self, mock_get):
        """Test getting source channels from API."""
        self.config.events_source = "api"
        test_channels = [
            {"name": "Channel 1", "type": "email"},
            {"name": "Channel 2", "type": "slack"}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_channels
        mock_get.return_value = mock_response
        
        channels = self.migrator._get_source_channels()
        
        assert channels == test_channels
        mock_get.assert_called_once_with(
            f"{self.config.source_url}{self.migrator.req_alert_channels}",
            headers=self.config.get_source_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_source_channels_api_error(self, mock_get):
        """Test handling API error when getting source channels."""
        self.config.events_source = "api"
        
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        channels = self.migrator._get_source_channels()
        
        assert channels is None

    def test_get_source_channels_file_not_found(self):
        """Test handling file not found error when getting source channels."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            channels = self.migrator._get_source_channels()
            
            assert channels is None

    def test_get_source_channels_invalid_json(self):
        """Test handling invalid JSON when getting source channels."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            channels = self.migrator._get_source_channels()
            
            assert channels is None

    @patch('migrator.requests.get')
    def test_get_target_channels(self, mock_get):
        """Test getting target channels."""
        test_channels = [
            {"name": "Existing Channel 1", "id": "1"},
            {"name": "Existing Channel 2", "id": "2"}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_channels
        mock_get.return_value = mock_response
        
        channels = self.migrator._get_target_channels()
        
        assert channels == test_channels
        mock_get.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_channels}",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_target_channels_error(self, mock_get):
        """Test handling error when getting target channels."""
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        channels = self.migrator._get_target_channels()
        
        assert channels is None

    @patch('builtins.input', return_value='s')
    def test_prompt_for_duplicate_channel_skip(self, mock_input):
        """Test prompting for duplicate channel - skip choice."""
        choice = self.migrator._prompt_for_duplicate_channel("Test Channel")
        
        assert choice == "skip"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='u')
    def test_prompt_for_duplicate_channel_update(self, mock_input):
        """Test prompting for duplicate channel - update choice."""
        choice = self.migrator._prompt_for_duplicate_channel("Test Channel")
        
        assert choice == "update"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='c')
    def test_prompt_for_duplicate_channel_cancel(self, mock_input):
        """Test prompting for duplicate channel - cancel choice."""
        choice = self.migrator._prompt_for_duplicate_channel("Test Channel")
        
        assert choice == "cancel"
        mock_input.assert_called_once()

    @patch('builtins.input', side_effect=['invalid', 's'])
    def test_prompt_for_duplicate_channel_invalid_then_valid(self, mock_input):
        """Test prompting for duplicate channel - invalid input then valid."""
        choice = self.migrator._prompt_for_duplicate_channel("Test Channel")
        
        assert choice == "skip"
        assert mock_input.call_count == 2

    @patch('migrator.requests.post')
    def test_create_channel_success(self, mock_post):
        """Test successful channel creation."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new_id"}
        mock_post.return_value = mock_response
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is True
        mock_post.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_channels}",
            headers=self.config.get_target_headers(),
            json=channel,
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.post')
    def test_create_channel_failure(self, mock_post):
        """Test failed channel creation."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is False

    @patch('migrator.requests.post')
    def test_create_channel_exception(self, mock_post):
        """Test channel creation with exception."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_post.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_channel_success(self, mock_put):
        """Test successful channel update."""
        channel = {"name": "Test Channel", "type": "email"}
        target_channels = [{"name": "Test Channel", "id": "existing_id"}]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "existing_id"}
        mock_put.return_value = mock_response
        
        result = self.migrator._update_channel(channel, "Test Channel", target_channels)
        
        assert result is True
        mock_put.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_channels}/existing_id",
            headers=self.config.get_target_headers(),
            json=channel,
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.put')
    def test_update_channel_not_found(self, mock_put):
        """Test channel update when target channel not found."""
        channel = {"name": "Test Channel", "type": "email"}
        target_channels = [{"name": "Other Channel", "id": "other_id"}]
        
        result = self.migrator._update_channel(channel, "Test Channel", target_channels)
        
        assert result is False
        mock_put.assert_not_called()

    @patch('migrator.requests.put')
    def test_update_channel_failure(self, mock_put):
        """Test failed channel update."""
        channel = {"name": "Test Channel", "type": "email"}
        target_channels = [{"name": "Test Channel", "id": "existing_id"}]
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_put.return_value = mock_response
        
        result = self.migrator._update_channel(channel, "Test Channel", target_channels)
        
        assert result is False

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_prompt_for_duplicate_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_success(self, mock_create, mock_prompt, mock_get_target, mock_get_source):
        """Test successful migration."""
        source_channels = [
            {"name": "Channel 1", "type": "email"},
            {"name": "Channel 2", "type": "slack"}
        ]
        target_channels = []
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 2, "updated": 0, "skipped": 0}
        assert mock_create.call_count == 2

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_prompt_for_duplicate_channel')
    @patch.object(AlertChannelsMigrator, '_update_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_with_duplicates(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with duplicate channels."""
        source_channels = [
            {"name": "Channel 1", "type": "email"},
            {"name": "Channel 2", "type": "slack"}
        ]
        target_channels = [{"name": "Channel 1", "id": "existing_id"}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels
        mock_prompt.return_value = "update"
        mock_update.return_value = True
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 1, "updated": 1, "skipped": 0}
        mock_update.assert_called_once()

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    def test_migrate_no_source_channels(self, mock_get_source):
        """Test migration when no source channels exist."""
        mock_get_source.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    def test_migrate_no_target_channels(self, mock_get_target, mock_get_source):
        """Test migration when target channels cannot be retrieved."""
        source_channels = [{"name": "Channel 1", "type": "email"}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 1, "migrated": 0, "updated": 0, "skipped": 0}

    def test_migrate_skip_channel_without_name(self):
        """Test that channels without name are skipped."""
        source_channels = [
            {"type": "email"},
            {"name": "Channel 2", "type": "slack"}
        ]
        target_channels = []
        
        with patch.object(self.migrator, '_get_source_channels', return_value=source_channels):
            with patch.object(self.migrator, '_get_target_channels', return_value=target_channels):
                with patch.object(self.migrator, '_create_channel', return_value=True):
                    result = self.migrator.migrate()
                    
                    assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped": 0}
