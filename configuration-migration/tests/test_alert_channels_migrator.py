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

    def test_channels_are_identical_true(self):
        """Channels with equal content (ignoring id, rbacTags, instanaUrl, apiTokenId) are identical."""
        source = {"name": "C", "kind": "EMAIL", "emails": ["a@b.com"], "id": "src-1", "rbacTags": ["x"]}
        target = {"name": "C", "kind": "EMAIL", "emails": ["a@b.com"], "id": "tgt-99"}
        assert self.migrator._channels_are_identical(source, target) is True

    def test_channels_are_identical_ignores_instana_url(self):
        """Channels differing only in instanaUrl are considered identical — it is always rewritten."""
        source = {"name": "C", "kind": "BIDIRECTIONAL_MS_TEAMS", "instanaUrl": "https://source.io", "channelName": "ch"}
        target = {"name": "C", "kind": "BIDIRECTIONAL_MS_TEAMS", "instanaUrl": "<invalid instanaUrl>", "channelName": "ch"}
        assert self.migrator._channels_are_identical(source, target) is True

    def test_channels_are_identical_ignores_api_token_id(self):
        """Channels differing only in apiTokenId are considered identical — it is backend-local."""
        source = {"name": "C", "kind": "BIDIRECTIONAL_MS_TEAMS", "apiTokenId": "src-token", "channelName": "ch"}
        target = {"name": "C", "kind": "BIDIRECTIONAL_MS_TEAMS", "apiTokenId": "tgt-token", "channelName": "ch"}
        assert self.migrator._channels_are_identical(source, target) is True

    def test_channels_are_identical_false_content_differs(self):
        """Channels with differing meaningful content are not identical."""
        source = {"name": "C", "kind": "EMAIL", "emails": ["a@b.com"], "id": "src-1"}
        target = {"name": "C", "kind": "EMAIL", "emails": ["z@z.com"], "id": "tgt-99"}
        assert self.migrator._channels_are_identical(source, target) is False

    def test_format_channel_preserves_id(self):
        """_format_channel_for_api must keep the id field — it is mandatory in the POST/PUT body."""
        channel = {"id": "source-id-123", "name": "C", "kind": "EMAIL", "emails": ["a@b.com"]}
        formatted = self.migrator._format_channel_for_api(channel)
        assert formatted["id"] == "source-id-123"

    def test_format_channel_strips_rbac_tags(self):
        """_format_channel_for_api must remove rbacTags."""
        channel = {"name": "C", "kind": "EMAIL", "emails": ["a@b.com"], "rbacTags": ["tag1"]}
        formatted = self.migrator._format_channel_for_api(channel)
        assert "rbacTags" not in formatted

    def test_format_channel_does_not_mutate_original(self):
        """_format_channel_for_api must not modify the original dict."""
        channel = {"id": "src", "name": "C", "kind": "EMAIL", "emails": ["a@b.com"]}
        self.migrator._format_channel_for_api(channel)
        assert "id" in channel

    def test_format_bidirectional_ms_teams_rewrites_instana_url(self):
        """BIDIRECTIONAL_MS_TEAMS: instanaUrl must be overwritten with the target URL."""
        channel = {
            "id": "src-1", "kind": "BIDIRECTIONAL_MS_TEAMS", "name": "T",
            "instanaUrl": "https://source.instana.io",  # source URL — must be replaced
            "apiTokenId": "tok", "channelId": "cid", "channelName": "ch",
            "serviceUrl": "https://smba.example.com", "teamId": "tid",
            "teamName": "team", "tenantId": "tnid", "tenantName": "tn",
        }
        formatted = self.migrator._format_channel_for_api(channel)
        assert formatted["instanaUrl"] == self.config.target_url

    def test_format_service_now_rewrites_instana_url_when_null(self):
        """SERVICE_NOW_APPLICATION: instanaUrl must be set to the target URL even when null in source."""
        channel = {
            "id": "src-2", "kind": "SERVICE_NOW_APPLICATION", "name": "SN",
            "instanaUrl": None,  # null in source — must be replaced
            "serviceNowUrl": "https://example.service-now.com",
        }
        formatted = self.migrator._format_channel_for_api(channel)
        assert formatted["instanaUrl"] == self.config.target_url

    def test_format_service_now_rewrites_instana_url_when_set_to_source(self):
        """SERVICE_NOW_APPLICATION: instanaUrl must be overwritten even when already set to source URL."""
        channel = {
            "id": "src-3", "kind": "SERVICE_NOW_APPLICATION", "name": "SN",
            "instanaUrl": "https://source.instana.io",  # source URL — must be replaced
            "serviceNowUrl": "https://example.service-now.com",
        }
        formatted = self.migrator._format_channel_for_api(channel)
        assert formatted["instanaUrl"] == self.config.target_url

    @patch('migrator.requests.post')
    def test_create_channel_success(self, mock_post):
        """Test successful channel creation."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": "new_id"}
        mock_post.return_value = mock_response
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is True

    @patch('migrator.requests.post')
    def test_create_channel_failure(self, mock_post):
        """Test failed channel creation (non-OK HTTP response)."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is False

    @patch('migrator.requests.post')
    def test_create_channel_exception(self, mock_post):
        """Test channel creation with network exception."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_post.side_effect = requests.exceptions.RequestException("API Error")
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is False

    @patch('migrator.requests.post')
    def test_create_channel_exception_with_response_body(self, mock_post):
        """Test that the server error body is included when an HTTP exception carries a response."""
        channel = {"name": "Test Channel", "type": "email"}
        
        mock_response = MagicMock()
        mock_response.text = "Internal Server Error detail"
        exc = requests.exceptions.HTTPError("500 Server Error", response=mock_response)
        mock_post.side_effect = exc
        
        result = self.migrator._create_channel(channel, "Test Channel")
        
        assert result is False

    @patch('migrator.requests.put')
    def test_update_channel_success(self, mock_put):
        """Test successful channel update. PUT body must carry the target id, not the source id."""
        channel = {"name": "Test Channel", "type": "email", "id": "source_id"}
        target_channel = {"name": "Test Channel", "id": "existing_id"}

        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "existing_id"}
        mock_put.return_value = mock_response

        result = self.migrator._update_channel(channel, "Test Channel", target_channel)

        assert result is True
        # The PUT body must use the target id, not the source id
        call_kwargs = mock_put.call_args
        sent_body = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
        assert sent_body["id"] == "existing_id"
        mock_put.assert_called_once_with(
            f"{self.config.target_url}{self.migrator.req_alert_channels}/existing_id",
            headers=self.config.get_target_headers(),
            json=sent_body,
            verify=self.config.verify_ssl
        )

    @patch('migrator.requests.put')
    def test_update_channel_no_id(self, mock_put):
        """Test channel update when the resolved target channel has no id."""
        channel = {"name": "Test Channel", "type": "email"}
        target_channel = {"name": "Test Channel"}  # missing id

        result = self.migrator._update_channel(channel, "Test Channel", target_channel)

        assert result is False
        mock_put.assert_not_called()

    @patch('migrator.requests.put')
    def test_update_channel_failure(self, mock_put):
        """Test failed channel update (non-OK HTTP response)."""
        channel = {"name": "Test Channel", "type": "email"}
        target_channel = {"name": "Test Channel", "id": "existing_id"}

        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_put.return_value = mock_response

        result = self.migrator._update_channel(channel, "Test Channel", target_channel)

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
        
        assert result == {"source": 2, "migrated": 2, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}
        assert mock_create.call_count == 2

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_prompt_for_duplicate_channel')
    @patch.object(AlertChannelsMigrator, '_update_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_with_duplicates(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Test migration with duplicate channels where user chooses update."""
        source_channels = [
            {"name": "Channel 1", "kind": "EMAIL", "emails": ["different@example.com"]},
            {"name": "Channel 2", "type": "slack"}
        ]
        target_channels = [{"name": "Channel 1", "id": "existing_id", "kind": "EMAIL", "emails": ["old@example.com"]}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels
        mock_prompt.return_value = "update"
        mock_update.return_value = True
        mock_create.return_value = True
        
        result = self.migrator.migrate()
        
        assert result == {"source": 2, "migrated": 1, "updated": 1, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}
        mock_update.assert_called_once()

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_update_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_identical_channel_skipped_silently(self, mock_create, mock_update, mock_get_target, mock_get_source):
        """Identical channels are skipped without prompting the user."""
        channel = {"name": "Channel 1", "kind": "EMAIL", "emails": ["a@b.com"]}
        source_channels = [channel]
        # Target has same content, different id — matched by name fallback
        target_channels = [dict(channel, id="tgt-1")]

        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels

        result = self.migrator.migrate()

        assert result["skipped_identical"] == 1
        assert result["skipped_user"] == 0
        mock_create.assert_not_called()
        mock_update.assert_not_called()

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_update_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_id_match_takes_priority_over_name_match(self, mock_create, mock_update, mock_get_target, mock_get_source):
        """When source id exists in target, that entry is used for comparison even if another
        target entry shares the same name but has different content."""
        # Source: one channel, id=A, emojiRendering=False
        source_channels = [
            {"id": "A", "name": "Chan", "kind": "SLACK", "emojiRendering": False}
        ]
        # Target: two channels with the same name but different ids/content.
        # The name-map would land on id=B (last seen), but the id-map correctly
        # resolves to id=A — which is identical — so it must silently skip.
        target_channels = [
            {"id": "A", "name": "Chan", "kind": "SLACK", "emojiRendering": False},
            {"id": "B", "name": "Chan", "kind": "SLACK", "emojiRendering": True},
        ]

        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels

        result = self.migrator.migrate()

        assert result["skipped_identical"] == 1
        mock_create.assert_not_called()
        mock_update.assert_not_called()

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_failed_create_increments_failed_count(self, mock_create, mock_get_target, mock_get_source):
        """Failed creates increment the failed counter."""
        source_channels = [{"name": "Channel 1", "type": "email"}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = []
        mock_create.return_value = False
        
        result = self.migrator.migrate()
        
        assert result["failed"] == 1
        assert result["migrated"] == 0

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    @patch.object(AlertChannelsMigrator, '_prompt_for_duplicate_channel')
    @patch.object(AlertChannelsMigrator, '_update_channel')
    @patch.object(AlertChannelsMigrator, '_create_channel')
    def test_migrate_failed_update_increments_failed_count(self, mock_create, mock_update, mock_prompt, mock_get_target, mock_get_source):
        """Failed updates increment the failed counter and do not fall through to create."""
        source_channels = [{"id": "s1", "name": "Channel 1", "kind": "EMAIL", "emails": ["different@x.com"]}]
        target_channels = [{"id": "s1", "name": "Channel 1", "kind": "EMAIL", "emails": ["old@x.com"]}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = target_channels
        mock_prompt.return_value = "update"
        mock_update.return_value = False
        
        result = self.migrator.migrate()
        
        assert result["failed"] == 1
        assert result["updated"] == 0
        # Must NOT fall through to create
        mock_create.assert_not_called()

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    def test_migrate_no_source_channels(self, mock_get_source):
        """Test migration when no source channels exist."""
        mock_get_source.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}

    @patch.object(AlertChannelsMigrator, '_get_source_channels')
    @patch.object(AlertChannelsMigrator, '_get_target_channels')
    def test_migrate_no_target_channels(self, mock_get_target, mock_get_source):
        """Test migration when target channels cannot be retrieved."""
        source_channels = [{"name": "Channel 1", "type": "email"}]
        
        mock_get_source.return_value = source_channels
        mock_get_target.return_value = None
        
        result = self.migrator.migrate()
        
        assert result == {"source": 1, "migrated": 0, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}

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
                    
                    assert result == {"source": 2, "migrated": 1, "updated": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "failed": 0}
