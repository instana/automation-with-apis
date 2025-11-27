"""Unit tests for the EventsMigrator class."""

import pytest
import json
import tempfile
import os
import requests
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'custom-events-specification'))
from migrator import EventsMigrator
from config import Config


class TestEventsMigrator:
    """Test cases for the EventsMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_events.json"
        
        self.migrator = EventsMigrator(self.config)

    def test_init(self):
        """Test migrator initialization."""
        assert self.migrator.config == self.config
        assert self.migrator.req_custom_events == "/api/events/settings/event-specifications/custom"

    @patch('migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        migrator = EventsMigrator(self.config)
        
        mock_disable_warnings.assert_called_once()

    def test_get_source_events_from_file(self):
        """Test getting source events from file."""
        test_events = [
            {"name": "Test Event 1", "query": "test query 1"},
            {"name": "Test Event 2", "query": "test query 2"}
        ]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(test_events))):
            events = self.migrator._get_source_events()
            
            assert events == test_events

    @patch('migrator.requests.get')
    def test_get_source_events_from_api(self, mock_get):
        """Test getting source events from API."""
        self.config.events_source = "api"
        test_events = [
            {"name": "Test Event 1", "query": "test query 1"},
            {"name": "Test Event 2", "query": "test query 2"}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_events
        mock_get.return_value = mock_response
        
        events = self.migrator._get_source_events()
        
        assert events == test_events
        mock_get.assert_called_once_with(
            f"{self.config.source_url}{self.migrator.req_custom_events}",
            headers=self.config.get_source_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_source_events_api_error(self, mock_get):
        """Test handling API error when getting source events."""
        self.config.events_source = "api"
        
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        events = self.migrator._get_source_events()
        
        assert events is None

    def test_get_source_events_file_not_found(self):
        """Test handling file not found error when getting source events."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            events = self.migrator._get_source_events()
            
            assert events is None

    def test_get_source_events_invalid_json(self):
        """Test handling invalid JSON when getting source events."""
        with patch('builtins.open', mock_open(read_data="invalid json")):
            events = self.migrator._get_source_events()
            
            assert events is None

    @patch('migrator.requests.get')
    def test_get_target_events(self, mock_get):
        """Test getting target events."""
        test_events = [
            {"name": "Existing Event 1", "id": "1"},
            {"name": "Existing Event 2", "id": "2"}
        ]
        
        mock_response = MagicMock()
        mock_response.json.return_value = test_events
        mock_get.return_value = mock_response
        
        events = self.migrator._get_target_events()
        
        assert events == test_events
        mock_get.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_custom_events}",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.get')
    def test_get_target_events_error(self, mock_get):
        """Test handling error when getting target events."""
        mock_get.side_effect = requests.exceptions.RequestException("API Error")
        
        events = self.migrator._get_target_events()
        
        assert events is None

    @patch('builtins.input', return_value='s')
    def test_prompt_for_duplicate_event_skip(self, mock_input):
        """Test prompting for duplicate event - skip choice."""
        choice = self.migrator._prompt_for_duplicate_event("Test Event")
        
        assert choice == "skip"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='u')
    def test_prompt_for_duplicate_event_update(self, mock_input):
        """Test prompting for duplicate event - update choice."""
        choice = self.migrator._prompt_for_duplicate_event("Test Event")
        
        assert choice == "update"
        mock_input.assert_called_once()

    @patch('builtins.input', return_value='c')
    def test_prompt_for_duplicate_event_cancel(self, mock_input):
        """Test prompting for duplicate event - cancel choice."""
        choice = self.migrator._prompt_for_duplicate_event("Test Event")
        
        assert choice == "cancel"
        mock_input.assert_called_once()

    @patch('builtins.input', side_effect=['invalid', 's'])
    def test_prompt_for_duplicate_event_invalid_then_valid(self, mock_input):
        """Test prompting for duplicate event - invalid input then valid."""
        choice = self.migrator._prompt_for_duplicate_event("Test Event")
        
        assert choice == "skip"
        assert mock_input.call_count == 2

    @patch('migrator.requests.post')
    def test_create_event_success(self, mock_post):
        """Test successful event creation."""
        event = {"name": "Test Event", "query": "test query"}
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new_id"}
        mock_post.return_value = mock_response
        
        result = self.migrator._create_event(event, "Test Event")
        
        assert result is True
        mock_post.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_custom_events}",
            headers=self.config.get_target_headers(),
            json=event,
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.post')
    def test_create_event_failure(self, mock_post):
        """Test failed event creation."""
        event = {"name": "Test Event", "query": "test query"}
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response
        
        result = self.migrator._create_event(event, "Test Event")
        
        assert result is False

    @patch('migrator.requests.post')
    def test_create_event_exception(self, mock_post):
        """Test event creation with exception."""
        event = {"name": "Test Event", "query": "test query"}
        
        mock_post.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._create_event(event, "Test Event")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_event_success(self, mock_put):
        """Test successful event update."""
        event = {"name": "Test Event", "query": "updated query"}
        target_events = [{"name": "Test Event", "id": "existing_id"}]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "existing_id"}
        mock_put.return_value = mock_response
        
        result = self.migrator._update_event(event, "Test Event", target_events)
        
        assert result is True
        mock_put.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_custom_events}/existing_id",
            headers=self.config.get_target_headers(),
            json=event,
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.put')
    def test_update_event_not_found(self, mock_put):
        """Test event update when target event not found."""
        event = {"name": "Test Event", "query": "updated query"}
        target_events = [{"name": "Other Event", "id": "other_id"}]
        
        result = self.migrator._update_event(event, "Test Event", target_events)
        
        assert result is False
        mock_put.assert_not_called()

    @patch('migrator.requests.put')
    def test_update_event_failure(self, mock_put):
        """Test failed event update."""
        event = {"name": "Test Event", "query": "updated query"}
        target_events = [{"name": "Test Event", "id": "existing_id"}]
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_put.return_value = mock_response
        
        result = self.migrator._update_event(event, "Test Event", target_events)
        
        assert result is False

    @patch.object(EventsMigrator, '_get_source_events')
    @patch.object(EventsMigrator, '_get_target_events')
    @patch.object(EventsMigrator, '_prompt_for_duplicate_event')
    @patch.object(EventsMigrator, '_create_event')
    def test_migrate_success(self, mock_create, mock_prompt, mock_get_target, mock_get_source):
        """Test successful migration."""
        source_events = [
            {"name": "Event 1", "query": "query 1"},
            {"name": "Event 2", "query": "query 2"}
        ]
        target_events = []
        
        mock_get_source.return_value = source_events
        mock_get_target.return_value = target_events
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 2, "updated": 0, "skipped": 0}
        assert mock_create.call_count == 2

    @patch.object(EventsMigrator, '_get_source_events')
    @patch.object(EventsMigrator, '_get_target_events')
    @patch.object(EventsMigrator, '_prompt_for_duplicate_event')
    @patch.object(EventsMigrator, '_update_event')
    @patch.object(EventsMigrator, '_create_event')
    def test_migrate_with_duplicates(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with duplicate events."""
        source_events = [
            {"name": "Event 1", "query": "query 1"},
            {"name": "Event 2", "query": "query 2"}
        ]
        target_events = [{"name": "Event 1", "id": "existing_id"}]
        
        mock_get_source.return_value = source_events
        mock_get_target.return_value = target_events
        mock_prompt.return_value = "update"
        mock_update.return_value = True
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 1, "updated": 1, "skipped": 0}
        mock_update.assert_called_once()

    @patch.object(EventsMigrator, '_get_source_events')
    def test_migrate_no_source_events(self, mock_get_source):
        """Test migration when no source events exist."""
        mock_get_source.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 0, "migrated": 0, "skipped": 0}

    @patch.object(EventsMigrator, '_get_source_events')
    @patch.object(EventsMigrator, '_get_target_events')
    def test_migrate_no_target_events(self, mock_get_target, mock_get_source):
        """Test migration when target events cannot be retrieved."""
        source_events = [{"name": "Event 1", "query": "query 1"}]
        
        mock_get_source.return_value = source_events
        mock_get_target.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 1, "migrated": 0, "skipped": 0}

    def test_migrate_skip_event_with_id_reference(self):
        """Test that events with .id in query are skipped."""
        source_events = [
            {"name": "Event 1", "query": "entity.id == 'test'"},
            {"name": "Event 2", "query": "normal query"}
        ]
        target_events = []
        
        with patch.object(self.migrator, '_get_source_events', return_value=source_events):
            with patch.object(self.migrator, '_get_target_events', return_value=target_events):
                with patch.object(self.migrator, '_create_event', return_value=True):
                    result = self.migrator.migrate()
                    
                    assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped": 1}

    def test_migrate_skip_event_without_name(self):
        """Test that events without name are skipped."""
        source_events = [
            {"query": "query 1"},
            {"name": "Event 2", "query": "query 2"}
        ]
        target_events = []
        
        with patch.object(self.migrator, '_get_source_events', return_value=source_events):
            with patch.object(self.migrator, '_get_target_events', return_value=target_events):
                with patch.object(self.migrator, '_create_event', return_value=True):
                    result = self.migrator.migrate()
                    
                    assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped": 0}
