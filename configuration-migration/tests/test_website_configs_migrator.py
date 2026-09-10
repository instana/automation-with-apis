"""Unit tests for the WebsiteConfigMigrator class."""

import pytest
import json
import requests
from unittest.mock import patch, mock_open, MagicMock, call
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "website-configs"))
from migrator import WebsiteConfigMigrator
from config import Config


class TestWebsiteConfigMigrator:
    """Test cases for the WebsiteConfigMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_websites.json"
        self.config.on_duplicate = "ask"

        self.migrator = WebsiteConfigMigrator(self.config)

    # ── __init__ ──────────────────────────────────────────────────────────────

    def test_init(self):
        """Test migrator initialisation stores config and sets the API path."""
        assert self.migrator.config == self.config
        assert self.migrator.req_website_config == "/api/website-monitoring/config"

    @patch("migrator.urllib3.disable_warnings")
    def test_init_ssl_disabled(self, mock_disable_warnings):
        """SSL warnings are suppressed when verify_ssl is False."""
        self.config.verify_ssl = False
        WebsiteConfigMigrator(self.config)
        mock_disable_warnings.assert_called_once()

    # ── _get_source_website_config ────────────────────────────────────────────

    def test_get_source_from_file_success(self):
        """Source websites are loaded from file when events_source='file'."""
        websites = [{"id": "w1", "name": "Site A"}, {"id": "w2", "name": "Site B"}]
        self.config.events_source = "file"

        with patch("builtins.open", mock_open(read_data=json.dumps(websites))):
            result = self.migrator._get_source_website_config()

        assert result == websites

    def test_get_source_from_file_case_insensitive(self):
        """File-source check is case-insensitive ('FILE', 'File', 'file' all work)."""
        websites = [{"id": "w1", "name": "Site A"}]
        for variant in ("FILE", "File", "file"):
            self.config.events_source = variant
            with patch("builtins.open", mock_open(read_data=json.dumps(websites))):
                result = self.migrator._get_source_website_config()
            assert result == websites, f"Failed for events_source='{variant}'"

    def test_get_source_from_file_not_found(self):
        """Returns None (not []) when the source file does not exist."""
        self.config.events_source = "file"
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = self.migrator._get_source_website_config()
        assert result is None

    def test_get_source_from_file_invalid_json(self):
        """Returns None when the source file contains invalid JSON."""
        self.config.events_source = "file"
        with patch("builtins.open", mock_open(read_data="not-json")):
            result = self.migrator._get_source_website_config()
        assert result is None

    @patch("migrator.requests.get")
    def test_get_source_from_api_success(self, mock_get):
        """Source websites are fetched from the source API and saved to file."""
        self.config.events_source = "api"
        websites = [{"id": "w1", "name": "Site A"}]
        mock_response = MagicMock()
        mock_response.json.return_value = websites
        mock_get.return_value = mock_response

        m = mock_open()
        with patch("builtins.open", m):
            result = self.migrator._get_source_website_config()

        assert result == websites
        mock_get.assert_called_once_with(
            f"{self.config.source_url}/api/website-monitoring/config",
            headers=self.config.get_source_headers(),
            verify=self.config.verify_ssl,
        )
        # Verify the response was written to file as a backup
        m.assert_called_with(self.config.events_file_path, "w")

    @patch("migrator.requests.get")
    def test_get_source_from_api_error(self, mock_get):
        """Returns None (not []) when the source API request fails."""
        self.config.events_source = "api"
        mock_get.side_effect = requests.exceptions.RequestException("connection error")

        result = self.migrator._get_source_website_config()

        assert result is None

    # ── _get_target_website_config ────────────────────────────────────────────

    @patch("migrator.requests.get")
    def test_get_target_success(self, mock_get):
        """Target websites are fetched from the target API."""
        websites = [{"id": "t1", "name": "Site A"}]
        mock_response = MagicMock()
        mock_response.json.return_value = websites
        mock_get.return_value = mock_response

        result = self.migrator._get_target_website_config()

        assert result == websites
        mock_get.assert_called_once_with(
            f"{self.config.target_url}/api/website-monitoring/config",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl,
        )

    @patch("migrator.requests.get")
    def test_get_target_api_error_returns_none(self, mock_get):
        """Returns None (not []) when the target API request fails."""
        mock_get.side_effect = requests.exceptions.RequestException("timeout")

        result = self.migrator._get_target_website_config()

        assert result is None

    # ── _build_website_mapping ────────────────────────────────────────────────

    def test_build_website_mapping_matches_by_name(self):
        """Source IDs are mapped to target IDs for websites with matching names."""
        source = [{"id": "s1", "name": "Alpha"}, {"id": "s2", "name": "Beta"}]
        target = [{"id": "t1", "name": "Alpha"}, {"id": "t3", "name": "Beta"}]

        mapping = self.migrator._build_website_mapping(source, target)

        assert mapping == {"s1": "t1", "s2": "t3"}

    def test_build_website_mapping_no_match(self):
        """Returns empty mapping when no names overlap."""
        source = [{"id": "s1", "name": "Alpha"}]
        target = [{"id": "t1", "name": "Gamma"}]

        mapping = self.migrator._build_website_mapping(source, target)

        assert mapping == {}

    def test_build_website_mapping_partial_match(self):
        """Only matching websites appear in the mapping."""
        source = [{"id": "s1", "name": "Alpha"}, {"id": "s2", "name": "Beta"}]
        target = [{"id": "t1", "name": "Alpha"}]

        mapping = self.migrator._build_website_mapping(source, target)

        assert mapping == {"s1": "t1"}
        assert "s2" not in mapping

    # ── _create_website_config ────────────────────────────────────────────────

    @patch("migrator.requests.post")
    def test_create_website_returns_target_id(self, mock_post):
        """Returns the new target ID from the POST response body."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "new-t1", "name": "Site A"}
        mock_post.return_value = mock_response

        result = self.migrator._create_website_config("Site A")

        assert result == "new-t1"
        mock_post.assert_called_once_with(
            f"{self.config.target_url}/api/website-monitoring/config?name=Site A",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl,
        )
        # No body should be sent (json= argument must not be present)
        call_kwargs = mock_post.call_args.kwargs
        assert "json" not in call_kwargs

    @patch("migrator.requests.post")
    def test_create_website_no_id_in_response_returns_none(self, mock_post):
        """Returns None when the POST response contains no 'id' field."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"name": "Site A"}  # no id
        mock_post.return_value = mock_response

        result = self.migrator._create_website_config("Site A")

        assert result is None

    @patch("migrator.requests.post")
    def test_create_website_api_error_returns_none(self, mock_post):
        """Returns None when the POST request fails."""
        mock_post.side_effect = requests.exceptions.RequestException("error")

        result = self.migrator._create_website_config("Site A")

        assert result is None

    # ── _update_website_config ────────────────────────────────────────────────

    @patch("migrator.requests.put")
    def test_update_website_success(self, mock_put):
        """Returns True and calls PUT with the correct URL on success."""
        mock_response = MagicMock()
        mock_put.return_value = mock_response

        result = self.migrator._update_website_config("Site A", "t-existing")

        assert result is True
        mock_put.assert_called_once_with(
            f"{self.config.target_url}/api/website-monitoring/config/t-existing?name=Site A",
            headers=self.config.get_target_headers(),
            verify=self.config.verify_ssl,
        )

    @patch("migrator.requests.put")
    def test_update_website_api_error_returns_false(self, mock_put):
        """Returns False when the PUT request fails."""
        mock_put.side_effect = requests.exceptions.RequestException("error")

        result = self.migrator._update_website_config("Site A", "t-existing")

        assert result is False

    # ── _prompt_for_duplicate_website ─────────────────────────────────────────

    def test_prompt_respects_on_duplicate_skip(self):
        """Returns 'skip' without stdin when config.on_duplicate='skip'."""
        self.config.on_duplicate = "skip"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "skip"

    def test_prompt_respects_on_duplicate_update(self):
        """Returns 'update' without stdin when config.on_duplicate='update'."""
        self.config.on_duplicate = "update"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "update"

    def test_prompt_respects_on_duplicate_cancel(self):
        """Returns 'cancel' without stdin when config.on_duplicate='cancel'."""
        self.config.on_duplicate = "cancel"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "cancel"

    @patch("builtins.input", return_value="s")
    def test_prompt_interactive_skip(self, _mock_input):
        """Interactive 's' input returns 'skip'."""
        self.config.on_duplicate = "ask"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "skip"

    @patch("builtins.input", return_value="u")
    def test_prompt_interactive_update(self, _mock_input):
        """Interactive 'u' input returns 'update'."""
        self.config.on_duplicate = "ask"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "update"

    @patch("builtins.input", return_value="c")
    def test_prompt_interactive_cancel(self, _mock_input):
        """Interactive 'c' input returns 'cancel'."""
        self.config.on_duplicate = "ask"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "cancel"

    @patch("builtins.input", side_effect=["invalid", "s"])
    def test_prompt_interactive_retries_on_invalid(self, _mock_input):
        """Interactive mode loops until a valid choice is entered."""
        self.config.on_duplicate = "ask"
        assert self.migrator._prompt_for_duplicate_website("Site A") == "skip"

    # ── migrate() ─────────────────────────────────────────────────────────────

    @patch.object(WebsiteConfigMigrator, "_get_source_website_config", return_value=None)
    def test_migrate_source_fetch_error(self, _mock_src):
        """Returns zeroed counts when source fetch fails (returns None)."""
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "website_mapping": {}}

    @patch.object(WebsiteConfigMigrator, "_get_source_website_config", return_value=[])
    def test_migrate_empty_source(self, _mock_src):
        """Returns zeroed counts when source returns an empty list."""
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "website_mapping": {}}

    @patch.object(WebsiteConfigMigrator, "_get_target_website_config", return_value=None)
    @patch.object(
        WebsiteConfigMigrator,
        "_get_source_website_config",
        return_value=[{"id": "s1", "name": "Site A"}],
    )
    def test_migrate_target_fetch_error(self, _mock_src, _mock_tgt):
        """Returns zeroed migration counts when target fetch fails (returns None)."""
        result = self.migrator.migrate()
        assert result["migrated"] == 0
        assert result["source"] == 1

    @patch.object(WebsiteConfigMigrator, "_create_website_config", return_value="new-t1")
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config", return_value=[])
    @patch.object(
        WebsiteConfigMigrator,
        "_get_source_website_config",
        return_value=[{"id": "s1", "name": "Site A"}],
    )
    def test_migrate_creates_new_website(self, _mock_src, _mock_tgt, mock_create):
        """New websites are created and their ID is stored in the mapping."""
        result = self.migrator.migrate()

        mock_create.assert_called_once_with("Site A")
        assert result["migrated"] == 1
        assert result["skipped"] == 0
        assert result["website_mapping"] == {"s1": "new-t1"}

    @patch.object(WebsiteConfigMigrator, "_create_website_config", return_value=None)
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config", return_value=[])
    @patch.object(
        WebsiteConfigMigrator,
        "_get_source_website_config",
        return_value=[{"id": "s1", "name": "Site A"}],
    )
    def test_migrate_create_failure_not_counted(self, _mock_src, _mock_tgt, mock_create):
        """Failed creations are not counted as migrated and not added to mapping."""
        result = self.migrator.migrate()

        assert result["migrated"] == 0
        assert result["website_mapping"] == {}

    @patch.object(WebsiteConfigMigrator, "_get_target_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_source_website_config")
    def test_migrate_skips_duplicate_on_config_skip(self, mock_src, mock_tgt):
        """Existing website is skipped when config.on_duplicate='skip'."""
        self.config.on_duplicate = "skip"
        mock_src.return_value = [{"id": "s1", "name": "Site A"}]
        mock_tgt.return_value = [{"id": "t1", "name": "Site A"}]

        result = self.migrator.migrate()

        assert result["skipped"] == 1
        assert result["migrated"] == 0

    @patch.object(WebsiteConfigMigrator, "_update_website_config", return_value=True)
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_source_website_config")
    def test_migrate_updates_duplicate_on_config_update(self, mock_src, mock_tgt, mock_update):
        """Existing website is updated when config.on_duplicate='update'."""
        self.config.on_duplicate = "update"
        mock_src.return_value = [{"id": "s1", "name": "Site A"}]
        mock_tgt.return_value = [{"id": "t1", "name": "Site A"}]

        result = self.migrator.migrate()

        mock_update.assert_called_once_with("Site A", "t1")
        assert result["updated"] == 1
        assert result["migrated"] == 0

    @patch.object(WebsiteConfigMigrator, "_create_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_source_website_config")
    def test_migrate_cancel_stops_loop(self, mock_src, mock_tgt, mock_create):
        """Migration loop stops when user chooses 'cancel' on a duplicate."""
        self.config.on_duplicate = "cancel"
        mock_src.return_value = [
            {"id": "s1", "name": "Site A"},
            {"id": "s2", "name": "Site B"},
        ]
        # Both exist in target — first cancel should stop after the first website
        mock_tgt.return_value = [
            {"id": "t1", "name": "Site A"},
            {"id": "t2", "name": "Site B"},
        ]

        result = self.migrator.migrate()

        mock_create.assert_not_called()
        assert result["migrated"] == 0

    @patch.object(WebsiteConfigMigrator, "_create_website_config", return_value="new-t2")
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_source_website_config")
    def test_migrate_skips_website_missing_name_or_id(self, mock_src, mock_tgt, mock_create):
        """Websites with missing name or id are silently skipped."""
        mock_src.return_value = [
            {"id": "s1"},              # missing name
            {"name": "Nameless"},      # missing id
            {"id": "s2", "name": "Site B"},
        ]
        mock_tgt.return_value = []

        result = self.migrator.migrate()

        mock_create.assert_called_once_with("Site B")
        assert result["migrated"] == 1

    @patch.object(WebsiteConfigMigrator, "_create_website_config", return_value="new-t1")
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config")
    @patch.object(WebsiteConfigMigrator, "_get_source_website_config")
    def test_migrate_no_extra_get_calls_per_website(self, mock_src, mock_tgt, mock_create):
        """_get_target_website_config is called exactly ONCE (not per created website)."""
        mock_src.return_value = [
            {"id": "s1", "name": "Alpha"},
            {"id": "s2", "name": "Beta"},
            {"id": "s3", "name": "Gamma"},
        ]
        mock_tgt.return_value = []

        self.migrator.migrate()

        # Should only be called once at the start, not once per new website
        mock_tgt.assert_called_once()

    @patch.object(WebsiteConfigMigrator, "_create_website_config", return_value="new-t1")
    @patch.object(WebsiteConfigMigrator, "_get_target_website_config", return_value=[])
    @patch.object(
        WebsiteConfigMigrator,
        "_get_source_website_config",
        return_value=[{"id": "s1", "name": "Site A"}],
    )
    def test_migrate_return_shape(self, _mock_src, _mock_tgt, _mock_create):
        """migrate() always returns a dict with all required keys."""
        result = self.migrator.migrate()
        for key in ("source", "migrated", "updated", "skipped", "website_mapping"):
            assert key in result, f"Key '{key}' missing from migrate() result"
