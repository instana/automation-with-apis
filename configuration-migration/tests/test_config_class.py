"""Unit tests for the Config class in config.py."""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


class TestConfigDefaults:
    """Tests for Config.__init__ default values."""

    def test_default_values(self):
        cfg = Config()
        assert cfg.source_token == ""
        assert cfg.source_url == ""
        assert cfg.target_token == ""
        assert cfg.target_url == ""
        assert cfg.verify_ssl is True
        assert cfg.events_source == "api"
        assert cfg.events_file_path == "source_events.json"
        assert cfg.default_owner_id is None
        assert cfg.on_duplicate == "ask"
        assert cfg.dry_run is False
        assert cfg.max_concurrent_requests == 10
        assert cfg.rate_limit_per_second == 50
        assert cfg.request_timeout == 30
        assert cfg.retry_attempts == 3


class TestConfigFromArgs:
    """Tests for Config.from_args()."""

    def test_minimal_args(self):
        cfg = Config.from_args([])
        # All defaults retained
        assert cfg.source_token == ""
        assert cfg.verify_ssl is True
        assert cfg.dry_run is False

    def test_source_and_target_args(self):
        cfg = Config.from_args([
            "--source-token", "src-tok",
            "--source-url", "https://source.example.com",
            "--target-token", "tgt-tok",
            "--target-url", "https://target.example.com",
        ])
        assert cfg.source_token == "src-tok"
        assert cfg.source_url == "https://source.example.com"
        assert cfg.target_token == "tgt-tok"
        assert cfg.target_url == "https://target.example.com"

    def test_no_verify_ssl_flag(self):
        cfg = Config.from_args(["--no-verify-ssl"])
        assert cfg.verify_ssl is False

    def test_events_source_file(self):
        cfg = Config.from_args(["--events-source", "file"])
        assert cfg.events_source == "file"

    def test_events_file_path(self):
        cfg = Config.from_args(["--events-file-path", "/tmp/events.json"])
        assert cfg.events_file_path == "/tmp/events.json"

    def test_default_owner_id(self):
        cfg = Config.from_args(["--default-owner-id", "user-123"])
        assert cfg.default_owner_id == "user-123"

    def test_on_duplicate_skip(self):
        cfg = Config.from_args(["--on-duplicate", "skip"])
        assert cfg.on_duplicate == "skip"

    def test_on_duplicate_update(self):
        cfg = Config.from_args(["--on-duplicate", "update"])
        assert cfg.on_duplicate == "update"

    def test_on_duplicate_cancel(self):
        cfg = Config.from_args(["--on-duplicate", "cancel"])
        assert cfg.on_duplicate == "cancel"

    def test_dry_run_flag(self):
        cfg = Config.from_args(["--dry-run"])
        assert cfg.dry_run is True

    def test_performance_tuning_args(self):
        cfg = Config.from_args([
            "--max-concurrent", "20",
            "--rate-limit", "100",
            "--request-timeout", "60",
            "--retry-attempts", "5",
        ])
        assert cfg.max_concurrent_requests == 20
        assert cfg.rate_limit_per_second == 100
        assert cfg.request_timeout == 60
        assert cfg.retry_attempts == 5

    def test_config_file_loaded(self, tmp_path):
        cfg_file = tmp_path / "test.ini"
        cfg_file.write_text(
            "[source]\ntoken = file-src-tok\nurl = https://src.example.com\n"
            "[target]\ntoken = file-tgt-tok\nurl = https://tgt.example.com\n"
        )
        cfg = Config.from_args(["--config-file", str(cfg_file)])
        assert cfg.source_token == "file-src-tok"
        assert cfg.source_url == "https://src.example.com"
        assert cfg.target_token == "file-tgt-tok"
        assert cfg.target_url == "https://tgt.example.com"

    def test_cli_args_override_config_file(self, tmp_path):
        cfg_file = tmp_path / "test.ini"
        cfg_file.write_text("[source]\ntoken = file-token\nurl = https://file-src.example.com\n")
        cfg = Config.from_args([
            "--config-file", str(cfg_file),
            "--source-token", "cli-token",
        ])
        # CLI overrides the file value
        assert cfg.source_token == "cli-token"
        assert cfg.source_url == "https://file-src.example.com"

    def test_env_vars_override_cli_args(self, monkeypatch):
        monkeypatch.setenv("EVENTS_MIGRATOR_SOURCE_TOKEN", "env-token")
        cfg = Config.from_args(["--source-token", "cli-token"])
        # Env vars take final precedence
        assert cfg.source_token == "env-token"

    def test_no_args_env_vars_not_set(self, monkeypatch):
        # Ensure no env vars interfere
        for key in [
            "EVENTS_MIGRATOR_SOURCE_TOKEN", "EVENTS_MIGRATOR_SOURCE_URL",
            "EVENTS_MIGRATOR_TARGET_TOKEN", "EVENTS_MIGRATOR_TARGET_URL",
        ]:
            monkeypatch.delenv(key, raising=False)
        cfg = Config.from_args([])
        assert cfg.source_token == ""


class TestConfigLoadFromFile:
    """Tests for Config.load_from_file()."""

    def test_file_not_found_raises(self):
        cfg = Config()
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            cfg.load_from_file("/nonexistent/path/config.ini")

    def test_loads_source_and_target(self, tmp_path):
        cfg_file = tmp_path / "cfg.ini"
        cfg_file.write_text(
            "[source]\ntoken = s-tok\nurl = https://s.example.com\n"
            "[target]\ntoken = t-tok\nurl = https://t.example.com\n"
        )
        cfg = Config()
        cfg.load_from_file(str(cfg_file))
        assert cfg.source_token == "s-tok"
        assert cfg.source_url == "https://s.example.com"
        assert cfg.target_token == "t-tok"
        assert cfg.target_url == "https://t.example.com"

    def test_loads_general_section(self, tmp_path):
        cfg_file = tmp_path / "cfg.ini"
        cfg_file.write_text(
            "[general]\n"
            "verify_ssl = false\n"
            "events_source = file\n"
            "events_file_path = /tmp/events.json\n"
            "default_owner_id = owner-1\n"
            "on_duplicate = skip\n"
            "dry_run = true\n"
            "max_concurrent_requests = 25\n"
            "rate_limit_per_second = 75\n"
            "request_timeout = 45\n"
            "retry_attempts = 5\n"
        )
        cfg = Config()
        cfg.load_from_file(str(cfg_file))
        assert cfg.verify_ssl is False
        assert cfg.events_source == "file"
        assert cfg.events_file_path == "/tmp/events.json"
        assert cfg.default_owner_id == "owner-1"
        assert cfg.on_duplicate == "skip"
        assert cfg.dry_run is True
        assert cfg.max_concurrent_requests == 25
        assert cfg.rate_limit_per_second == 75
        assert cfg.request_timeout == 45
        assert cfg.retry_attempts == 5

    def test_missing_sections_keep_defaults(self, tmp_path):
        cfg_file = tmp_path / "empty.ini"
        cfg_file.write_text("")
        cfg = Config()
        cfg.load_from_file(str(cfg_file))
        # All defaults preserved
        assert cfg.source_token == ""
        assert cfg.verify_ssl is True

    def test_partial_source_section(self, tmp_path):
        cfg_file = tmp_path / "partial.ini"
        cfg_file.write_text("[source]\ntoken = only-token\n")
        cfg = Config()
        cfg.load_from_file(str(cfg_file))
        assert cfg.source_token == "only-token"
        assert cfg.source_url == ""


class TestConfigLoadFromEnv:
    """Tests for Config.load_from_env()."""

    def test_loads_all_env_vars(self, monkeypatch):
        monkeypatch.setenv("EVENTS_MIGRATOR_SOURCE_TOKEN", "env-src")
        monkeypatch.setenv("EVENTS_MIGRATOR_SOURCE_URL", "https://env-src.com")
        monkeypatch.setenv("EVENTS_MIGRATOR_TARGET_TOKEN", "env-tgt")
        monkeypatch.setenv("EVENTS_MIGRATOR_TARGET_URL", "https://env-tgt.com")
        monkeypatch.setenv("EVENTS_MIGRATOR_VERIFY_SSL", "false")
        monkeypatch.setenv("EVENTS_MIGRATOR_EVENTS_SOURCE", "file")
        monkeypatch.setenv("EVENTS_MIGRATOR_EVENTS_FILE_PATH", "/tmp/e.json")
        monkeypatch.setenv("EVENTS_MIGRATOR_DEFAULT_OWNER_ID", "owner-99")
        monkeypatch.setenv("EVENTS_MIGRATOR_ON_DUPLICATE", "update")
        monkeypatch.setenv("EVENTS_MIGRATOR_DRY_RUN", "true")
        monkeypatch.setenv("EVENTS_MIGRATOR_MAX_CONCURRENT", "30")
        monkeypatch.setenv("EVENTS_MIGRATOR_RATE_LIMIT", "200")
        monkeypatch.setenv("EVENTS_MIGRATOR_REQUEST_TIMEOUT", "90")
        monkeypatch.setenv("EVENTS_MIGRATOR_RETRY_ATTEMPTS", "7")

        cfg = Config()
        cfg.load_from_env()

        assert cfg.source_token == "env-src"
        assert cfg.source_url == "https://env-src.com"
        assert cfg.target_token == "env-tgt"
        assert cfg.target_url == "https://env-tgt.com"
        assert cfg.verify_ssl is False
        assert cfg.events_source == "file"
        assert cfg.events_file_path == "/tmp/e.json"
        assert cfg.default_owner_id == "owner-99"
        assert cfg.on_duplicate == "update"
        assert cfg.dry_run is True
        assert cfg.max_concurrent_requests == 30
        assert cfg.rate_limit_per_second == 200
        assert cfg.request_timeout == 90
        assert cfg.retry_attempts == 7

    def test_verify_ssl_false_variants(self, monkeypatch):
        cfg = Config()
        monkeypatch.setenv("EVENTS_MIGRATOR_VERIFY_SSL", "false")
        cfg.load_from_env()
        assert cfg.verify_ssl is False

    def test_verify_ssl_non_false_remains_true(self, monkeypatch):
        cfg = Config()
        monkeypatch.setenv("EVENTS_MIGRATOR_VERIFY_SSL", "true")
        cfg.load_from_env()
        assert cfg.verify_ssl is True

    def test_dry_run_false_values(self, monkeypatch):
        for val in ("false", "0", ""):
            cfg = Config()
            monkeypatch.setenv("EVENTS_MIGRATOR_DRY_RUN", val)
            cfg.load_from_env()
            assert cfg.dry_run is False, f"Expected False for DRY_RUN='{val}'"

    def test_dry_run_true_value(self, monkeypatch):
        cfg = Config()
        monkeypatch.setenv("EVENTS_MIGRATOR_DRY_RUN", "1")
        cfg.load_from_env()
        assert cfg.dry_run is True

    def test_no_env_vars_set_keeps_defaults(self, monkeypatch):
        for key in [
            "EVENTS_MIGRATOR_SOURCE_TOKEN", "EVENTS_MIGRATOR_SOURCE_URL",
            "EVENTS_MIGRATOR_TARGET_TOKEN", "EVENTS_MIGRATOR_TARGET_URL",
            "EVENTS_MIGRATOR_VERIFY_SSL", "EVENTS_MIGRATOR_EVENTS_SOURCE",
            "EVENTS_MIGRATOR_EVENTS_FILE_PATH", "EVENTS_MIGRATOR_DEFAULT_OWNER_ID",
            "EVENTS_MIGRATOR_ON_DUPLICATE", "EVENTS_MIGRATOR_DRY_RUN",
            "EVENTS_MIGRATOR_MAX_CONCURRENT", "EVENTS_MIGRATOR_RATE_LIMIT",
            "EVENTS_MIGRATOR_REQUEST_TIMEOUT", "EVENTS_MIGRATOR_RETRY_ATTEMPTS",
        ]:
            monkeypatch.delenv(key, raising=False)
        cfg = Config()
        cfg.load_from_env()
        assert cfg.source_token == ""
        assert cfg.verify_ssl is True
        assert cfg.dry_run is False


class TestConfigValidate:
    """Tests for Config.validate()."""

    def _full_config(self):
        cfg = Config()
        cfg.source_token = "s-tok"
        cfg.source_url = "https://source.example.com"
        cfg.target_token = "t-tok"
        cfg.target_url = "https://target.example.com"
        return cfg

    def test_valid_api_mode_passes(self):
        cfg = self._full_config()
        cfg.validate()  # Should not raise

    def test_valid_file_mode_skips_source_credentials(self):
        cfg = Config()
        cfg.events_source = "file"
        cfg.target_token = "t-tok"
        cfg.target_url = "https://target.example.com"
        cfg.validate()  # Should not raise — source credentials not required

    def test_missing_source_token_raises(self):
        cfg = self._full_config()
        cfg.source_token = ""
        with pytest.raises(ValueError, match="Source API token is required"):
            cfg.validate()

    def test_missing_source_url_raises(self):
        cfg = self._full_config()
        cfg.source_url = ""
        with pytest.raises(ValueError, match="Source backend URL is required"):
            cfg.validate()

    def test_missing_target_token_raises(self):
        cfg = self._full_config()
        cfg.target_token = ""
        with pytest.raises(ValueError, match="Target API token is required"):
            cfg.validate()

    def test_missing_target_url_raises(self):
        cfg = self._full_config()
        cfg.target_url = ""
        with pytest.raises(ValueError, match="Target backend URL is required"):
            cfg.validate()

    def test_file_mode_still_requires_target_token(self):
        cfg = Config()
        cfg.events_source = "file"
        cfg.target_url = "https://target.example.com"
        # target_token is blank
        with pytest.raises(ValueError, match="Target API token is required"):
            cfg.validate()

    def test_file_mode_case_insensitive(self):
        cfg = Config()
        cfg.events_source = "FILE"
        cfg.target_token = "t-tok"
        cfg.target_url = "https://target.example.com"
        cfg.validate()  # Should not raise


class TestConfigHeaders:
    """Tests for Config.get_source_headers() and get_target_headers()."""

    def test_get_source_headers(self):
        cfg = Config()
        cfg.source_token = "src-token"
        headers = cfg.get_source_headers()
        assert headers["Authorization"] == "apiToken src-token"
        assert headers["Content-Type"] == "application/json"

    def test_get_target_headers(self):
        cfg = Config()
        cfg.target_token = "tgt-token"
        headers = cfg.get_target_headers()
        assert headers["Authorization"] == "apiToken tgt-token"
        assert headers["Content-Type"] == "application/json"

    def test_headers_reflect_current_token(self):
        cfg = Config()
        cfg.source_token = "initial"
        cfg.source_token = "updated"
        assert cfg.get_source_headers()["Authorization"] == "apiToken updated"
