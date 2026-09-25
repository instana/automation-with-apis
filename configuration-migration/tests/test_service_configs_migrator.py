"""Unit tests for the ServiceConfigMigrator class."""

import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "service-configuration"))
from migrator import ServiceConfigMigrator
from utils import print_api_error, prompt_duplicate
from config import Config

from instana_client.exceptions import ApiException


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_svc_cfg(name="My Service", cfg_id="svc-1", label="My Service",
                  enabled=True, match_specification=None, comment=None):
    """Return a minimal ServiceConfig mock."""
    cfg = MagicMock()
    cfg.id = cfg_id
    cfg.name = name
    cfg.label = label
    cfg.enabled = enabled
    cfg.match_specification = match_specification or []
    cfg.comment = comment
    cfg.to_dict.return_value = {
        "id": cfg_id,
        "name": name,
        "label": label,
        "enabled": enabled,
        "matchSpecification": match_specification or [],
        "comment": comment,
    }
    return cfg


def _raw_response(items: list) -> MagicMock:
    """Simulate the raw HTTP response returned by *_without_preload_content calls."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(items).encode()
    return mock


# ── tests ──────────────────────────────────────────────────────────────────────


class TestServiceConfigMigrator:
    """Tests for ServiceConfigMigrator."""

    def setup_method(self):
        self.config = Config()
        self.config.source_token = "src-token"
        self.config.source_url = "https://source.example.com"
        self.config.target_token = "tgt-token"
        self.config.target_url = "https://target.example.com"
        self.config.verify_ssl = True
        self.config.on_duplicate = "ask"

        self.migrator = ServiceConfigMigrator(self.config)

    # ── __init__ ───────────────────────────────────────────────────────────────

    def test_init_stores_config(self):
        assert self.migrator.config is self.config

    @patch("migrator.urllib3.disable_warnings")
    def test_init_disables_ssl_warnings_when_verify_ssl_false(self, mock_dw):
        self.config.verify_ssl = False
        ServiceConfigMigrator(self.config)
        mock_dw.assert_called_once()

    @patch("migrator.urllib3.disable_warnings")
    def test_init_does_not_disable_ssl_warnings_when_verify_ssl_true(self, mock_dw):
        ServiceConfigMigrator(self.config)
        mock_dw.assert_not_called()

    # ── print_api_error ───────────────────────────────────────────────────────

    def test_print_api_error_extracts_details(self, capsys):
        exc = ApiException(status=422, reason="Unprocessable Entity")
        exc.body = json.dumps({"details": "name is required"})
        print_api_error("✗ Prefix", exc)
        out = capsys.readouterr().out
        assert "422" in out
        assert "name is required" in out

    def test_print_api_error_falls_back_to_message(self, capsys):
        exc = ApiException(status=400, reason="Bad Request")
        exc.body = json.dumps({"message": "bad payload"})
        print_api_error("✗ Prefix", exc)
        assert "bad payload" in capsys.readouterr().out

    def test_print_api_error_handles_non_json_body(self, capsys):
        exc = ApiException(status=500, reason="Internal Server Error")
        exc.body = "raw error text"
        print_api_error("✗ Prefix", exc)
        assert "raw error text" in capsys.readouterr().out

    def test_print_api_error_handles_empty_body(self, capsys):
        exc = ApiException(status=503, reason="Service Unavailable")
        exc.body = ""
        print_api_error("✗ Prefix", exc)
        assert "503" in capsys.readouterr().out

    # ── _get_configs ───────────────────────────────────────────────────────────

    @patch("migrator.ServiceConfig")
    def test_get_configs_success(self, mock_model):
        api = MagicMock()
        item = {"name": "My Service", "label": "My Service", "enabled": True}
        api.get_service_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_svc_cfg("My Service")

        result = self.migrator._get_configs(api, "source")

        assert result is not None
        assert len(result) == 1
        mock_model.from_dict.assert_called_once_with(item)

    @patch("migrator.ServiceConfig")
    def test_get_configs_returns_empty_list_for_empty_response(self, mock_model):
        api = MagicMock()
        api.get_service_configs_without_preload_content.return_value = _raw_response([])

        result = self.migrator._get_configs(api, "target")

        assert result == []

    def test_get_configs_returns_none_on_exception(self):
        api = MagicMock()
        api.get_service_configs_without_preload_content.side_effect = Exception("timeout")

        result = self.migrator._get_configs(api, "source")

        assert result is None

    # ── _build_config_payload ──────────────────────────────────────────────────

    def test_build_payload_includes_required_fields(self):
        rule = MagicMock()
        rule.to_dict.return_value = {"type": "EQUALS", "key": "service.name", "value": "foo"}
        cfg = _make_svc_cfg("My Service", label="My Service", enabled=True,
                            match_specification=[rule])
        payload = self.migrator._build_config_payload(cfg)

        assert payload["name"] == "My Service"
        assert payload["label"] == "My Service"
        assert payload["enabled"] is True
        assert payload["matchSpecification"] == [rule.to_dict()]

    def test_build_payload_includes_comment_when_present(self):
        cfg = _make_svc_cfg(comment="my note")
        payload = self.migrator._build_config_payload(cfg)
        assert payload["comment"] == "my note"

    def test_build_payload_omits_comment_when_none(self):
        cfg = _make_svc_cfg(comment=None)
        payload = self.migrator._build_config_payload(cfg)
        assert "comment" not in payload

    def test_build_payload_serialises_all_match_rules(self):
        rule1 = MagicMock()
        rule1.to_dict.return_value = {"a": 1}
        rule2 = MagicMock()
        rule2.to_dict.return_value = {"b": 2}
        cfg = _make_svc_cfg(match_specification=[rule1, rule2])
        payload = self.migrator._build_config_payload(cfg)
        assert payload["matchSpecification"] == [{"a": 1}, {"b": 2}]

    # ── _create_config ─────────────────────────────────────────────────────────

    def test_create_config_returns_true_on_success(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = json.dumps({"id": "new-id"}).encode()
        api.add_service_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)
        cfg = _make_svc_cfg("My Service")

        result = self.migrator._create_config(api, cfg)

        assert result is True

    def test_create_config_returns_true_when_body_empty(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = b""
        api.add_service_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)
        cfg = _make_svc_cfg("My Service")

        assert self.migrator._create_config(api, cfg) is True

    def test_create_config_returns_false_on_api_exception(self):
        api = MagicMock()
        exc = ApiException(status=409, reason="Conflict")
        exc.body = json.dumps({"message": "already exists"})
        api.add_service_config_without_preload_content.__wrapped__ = MagicMock(side_effect=exc)
        cfg = _make_svc_cfg("My Service")

        assert self.migrator._create_config(api, cfg) is False

    def test_create_config_returns_false_on_generic_exception(self):
        api = MagicMock()
        api.add_service_config_without_preload_content.__wrapped__ = MagicMock(
            side_effect=RuntimeError("network error")
        )
        cfg = _make_svc_cfg("My Service")

        assert self.migrator._create_config(api, cfg) is False

    # ── _update_config ─────────────────────────────────────────────────────────

    def test_update_config_returns_true_on_success(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = json.dumps({"id": "svc-1"}).encode()
        api.put_service_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)

        src = _make_svc_cfg("My Service", cfg_id="src-1")
        tgt = _make_svc_cfg("My Service", cfg_id="svc-1")

        result = self.migrator._update_config(api, src, [tgt])

        assert result is True

    def test_update_config_uses_target_id_in_payload(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = json.dumps({"id": "svc-1"}).encode()
        wrapped = MagicMock(return_value=raw)
        api.put_service_config_without_preload_content.__wrapped__ = wrapped

        src = _make_svc_cfg("My Service", cfg_id="src-99")
        tgt = _make_svc_cfg("My Service", cfg_id="svc-1")

        self.migrator._update_config(api, src, [tgt])

        call_kwargs = wrapped.call_args.kwargs
        assert call_kwargs["id"] == "svc-1"
        assert call_kwargs["service_config"]["id"] == "svc-1"

    def test_update_config_returns_false_when_target_not_found(self):
        api = MagicMock()
        wrapped = MagicMock()
        api.put_service_config_without_preload_content.__wrapped__ = wrapped

        src = _make_svc_cfg("My Service")
        other = _make_svc_cfg("Other Service", cfg_id="other-1")

        result = self.migrator._update_config(api, src, [other])

        assert result is False
        wrapped.assert_not_called()

    def test_update_config_returns_false_on_api_exception(self):
        api = MagicMock()
        exc = ApiException(status=400, reason="Bad Request")
        exc.body = json.dumps({"message": "invalid"})
        api.put_service_config_without_preload_content.__wrapped__ = MagicMock(side_effect=exc)

        src = _make_svc_cfg("My Service", cfg_id="src-1")
        tgt = _make_svc_cfg("My Service", cfg_id="svc-1")

        assert self.migrator._update_config(api, src, [tgt]) is False

    # ── prompt_duplicate ───────────────────────────────────────────────────────

    @patch("utils.sys.stdin.isatty", return_value=False)
    def test_prompt_non_interactive_returns_skip(self, _):
        assert prompt_duplicate("Service config", "My Service") == "skip"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="s")
    def test_prompt_interactive_s_returns_skip(self, _, __):
        assert prompt_duplicate("Service config", "My Service") == "skip"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="u")
    def test_prompt_interactive_u_returns_update(self, _, __):
        assert prompt_duplicate("Service config", "My Service") == "update"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="c")
    def test_prompt_interactive_c_returns_cancel(self, _, __):
        assert prompt_duplicate("Service config", "My Service") == "cancel"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", side_effect=["bad", "skip"])
    def test_prompt_retries_on_invalid_then_accepts_full_word(self, _, __):
        assert prompt_duplicate("Service config", "My Service") == "skip"

    # ── migrate() ─────────────────────────────────────────────────────────────

    @patch.object(ServiceConfigMigrator, "_get_configs", return_value=None)
    def test_migrate_returns_zeros_when_source_fetch_fails(self, _):
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0, "skipped_identical": 0, "skipped_unsafe": 0, "skipped_user": 0, "skipped_invalid": 0, "failed": 0}

    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_returns_zeros_when_target_fetch_fails(self, mock_get):
        src = _make_svc_cfg("My Service")
        mock_get.side_effect = [[src], None]
        result = self.migrator.migrate()
        assert result["source"] == 1
        assert result["migrated"] == 0

    @patch.object(ServiceConfigMigrator, "_create_config", return_value=True)
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_creates_new_config(self, mock_get, mock_create):
        src = _make_svc_cfg("My Service")
        mock_get.side_effect = [[src], []]
        result = self.migrator.migrate()
        mock_create.assert_called_once()
        assert result["migrated"] == 1
        assert result["skipped"] == 0

    @patch.object(ServiceConfigMigrator, "_create_config", return_value=False)
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_counts_failed_create_as_failed(self, mock_get, _):
        src = _make_svc_cfg("My Service")
        mock_get.side_effect = [[src], []]
        result = self.migrator.migrate()
        assert result["migrated"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 1

    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_skips_duplicate_when_on_duplicate_skip(self, mock_get):
        self.config.on_duplicate = "skip"
        src = _make_svc_cfg("My Service")
        tgt = _make_svc_cfg("My Service", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["skipped"] == 1
        assert result["migrated"] == 0

    @patch.object(ServiceConfigMigrator, "_update_config", return_value=True)
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_updates_duplicate_when_on_duplicate_update(self, mock_get, mock_update):
        self.config.on_duplicate = "update"
        src = _make_svc_cfg("My Service")
        tgt = _make_svc_cfg("My Service", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        mock_update.assert_called_once()
        assert result["updated"] == 1
        assert result["migrated"] == 0

    @patch.object(ServiceConfigMigrator, "_update_config", return_value=False)
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_failed_update_counted_as_failed(self, mock_get, _):
        self.config.on_duplicate = "update"
        src = _make_svc_cfg("My Service")
        tgt = _make_svc_cfg("My Service", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 1

    @patch.object(ServiceConfigMigrator, "_create_config")
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_cancel_stops_loop(self, mock_get, mock_create):
        self.config.on_duplicate = "cancel"
        src1 = _make_svc_cfg("Svc A")
        src2 = _make_svc_cfg("Svc B")
        tgt1 = _make_svc_cfg("Svc A", cfg_id="t1")
        tgt2 = _make_svc_cfg("Svc B", cfg_id="t2")
        mock_get.side_effect = [[src1, src2], [tgt1, tgt2]]
        result = self.migrator.migrate()
        mock_create.assert_not_called()
        assert result["migrated"] == 0

    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_result_has_all_required_keys(self, mock_get):
        mock_get.side_effect = [[], []]
        result = self.migrator.migrate()
        for key in ("source", "migrated", "updated", "skipped"):
            assert key in result

    @patch.object(ServiceConfigMigrator, "_create_config", return_value=True)
    @patch.object(ServiceConfigMigrator, "_get_configs")
    def test_migrate_get_configs_called_exactly_twice(self, mock_get, _):
        mock_get.side_effect = [
            [_make_svc_cfg("A"), _make_svc_cfg("B")],
            [],
        ]
        self.migrator.migrate()
        assert mock_get.call_count == 2
