"""Unit tests for the ApplicationConfigMigrator class."""

import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest
import importlib.util

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
_app_dir = os.path.join(os.path.dirname(__file__), "..", "application-configuration")
_spec = importlib.util.spec_from_file_location("migrator", os.path.join(_app_dir, "migrator.py"))
migrator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrator)
sys.modules['migrator'] = migrator
ApplicationConfigMigrator = migrator.ApplicationConfigMigrator
_BUSINESS_CRITICALITY_INT_TO_STR = migrator._BUSINESS_CRITICALITY_INT_TO_STR
_BUSINESS_CRITICALITY_STR_TO_INT = migrator._BUSINESS_CRITICALITY_STR_TO_INT
from utils import print_api_error, prompt_duplicate
from config import Config

from instana_client.exceptions import ApiException


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_app_cfg(label="My App", cfg_id="app-1", boundary_scope="ALL",
                  business_criticality="NOT_DEFINED", scope=None,
                  access_rules=None, match_specification=None,
                  tag_filter_expression=None):
    """Return a minimal ApplicationConfig mock."""
    cfg = MagicMock()
    cfg.id = cfg_id
    cfg.label = label
    cfg.boundary_scope = boundary_scope
    cfg.business_criticality = business_criticality
    cfg.scope = scope
    cfg.access_rules = access_rules or []
    cfg.match_specification = match_specification
    cfg.tag_filter_expression = tag_filter_expression
    return cfg


def _raw_response(items: list) -> MagicMock:
    """Simulate the raw HTTP response returned by *_without_preload_content calls."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(items).encode()
    return mock


# ── fixture ────────────────────────────────────────────────────────────────────


class TestApplicationConfigMigrator:
    """Tests for ApplicationConfigMigrator."""

    def setup_method(self):
        sys.modules['migrator'] = migrator
        self.config = Config()
        self.config.source_token = "src-token"
        self.config.source_url = "https://source.example.com"
        self.config.target_token = "tgt-token"
        self.config.target_url = "https://target.example.com"
        self.config.verify_ssl = True
        self.config.on_duplicate = "ask"

        self.migrator = ApplicationConfigMigrator(self.config)

    # ── __init__ ───────────────────────────────────────────────────────────────

    def test_init_stores_config(self):
        assert self.migrator.config is self.config

    @patch("migrator.urllib3.disable_warnings")
    def test_init_disables_ssl_warnings_when_verify_ssl_false(self, mock_dw):
        self.config.verify_ssl = False
        ApplicationConfigMigrator(self.config)
        mock_dw.assert_called_once()

    @patch("migrator.urllib3.disable_warnings")
    def test_init_does_not_disable_ssl_warnings_when_verify_ssl_true(self, mock_dw):
        ApplicationConfigMigrator(self.config)
        mock_dw.assert_not_called()

    # ── businessCriticality maps ───────────────────────────────────────────────

    def test_int_to_str_map_covers_all_six_values(self):
        assert _BUSINESS_CRITICALITY_INT_TO_STR == {
            0: "NOT_DEFINED",
            1: "LOWEST",
            2: "LOW",
            3: "MEDIUM",
            4: "HIGH",
            5: "HIGHEST",
        }

    def test_str_to_int_map_is_exact_inverse(self):
        for i, s in _BUSINESS_CRITICALITY_INT_TO_STR.items():
            assert _BUSINESS_CRITICALITY_STR_TO_INT[s] == i

    # ── print_api_error ───────────────────────────────────────────────────────

    def test_print_api_error_extracts_details(self, capsys):
        exc = ApiException(status=422, reason="Unprocessable Entity")
        exc.body = json.dumps({"details": "field x is required"})
        print_api_error("✗ Prefix", exc)
        out = capsys.readouterr().out
        assert "422" in out
        assert "field x is required" in out

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

    @patch("migrator.ApplicationConfig")
    def test_get_configs_success(self, mock_model):
        api = MagicMock()
        item = {"label": "App A", "businessCriticality": "HIGH"}
        api.get_application_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_app_cfg("App A")

        result = self.migrator._get_configs(api, "source")

        assert result is not None
        assert len(result) == 1
        mock_model.from_dict.assert_called_once_with(item)

    @patch("migrator.ApplicationConfig")
    def test_get_configs_coerces_integer_business_criticality(self, mock_model):
        """Integer businessCriticality from legacy backends is converted to string."""
        api = MagicMock()
        item = {"label": "App A", "businessCriticality": 4}  # integer HIGH
        api.get_application_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_app_cfg("App A")

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["businessCriticality"] == "HIGH"

    @patch("migrator.ApplicationConfig")
    def test_get_configs_leaves_string_business_criticality_unchanged(self, mock_model):
        api = MagicMock()
        item = {"label": "App A", "businessCriticality": "MEDIUM"}
        api.get_application_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_app_cfg("App A")

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["businessCriticality"] == "MEDIUM"

    def test_get_configs_returns_none_on_exception(self):
        api = MagicMock()
        api.get_application_configs_without_preload_content.side_effect = Exception("timeout")

        result = self.migrator._get_configs(api, "source")

        assert result is None

    # ── _build_config_payload ──────────────────────────────────────────────────

    def test_build_payload_converts_str_criticality_to_int(self):
        cfg = _make_app_cfg(business_criticality="HIGH")
        payload = self.migrator._build_config_payload(cfg)
        assert payload["businessCriticality"] == 4

    def test_build_payload_passes_through_int_criticality(self):
        cfg = _make_app_cfg(business_criticality=3)
        payload = self.migrator._build_config_payload(cfg)
        assert payload["businessCriticality"] == 3

    def test_build_payload_includes_match_specification_when_present(self):
        match_spec = MagicMock()
        match_spec.to_dict.return_value = {"key": "entity.type", "value": "service"}
        cfg = _make_app_cfg(match_specification=match_spec)
        payload = self.migrator._build_config_payload(cfg)
        assert "matchSpecification" in payload

    def test_build_payload_omits_match_specification_when_none(self):
        cfg = _make_app_cfg(match_specification=None)
        payload = self.migrator._build_config_payload(cfg)
        assert "matchSpecification" not in payload

    def test_build_payload_includes_tag_filter_when_present(self):
        tag_filter = MagicMock()
        tag_filter.to_dict.return_value = {"type": "TAG_FILTER"}
        cfg = _make_app_cfg(tag_filter_expression=tag_filter)
        payload = self.migrator._build_config_payload(cfg)
        assert "tagFilterExpression" in payload

    def test_build_payload_omits_tag_filter_when_none(self):
        cfg = _make_app_cfg(tag_filter_expression=None)
        payload = self.migrator._build_config_payload(cfg)
        assert "tagFilterExpression" not in payload

    def test_build_payload_serialises_access_rules(self):
        rule = MagicMock()
        rule.to_dict.return_value = {"accessType": "READ"}
        cfg = _make_app_cfg(access_rules=[rule])
        payload = self.migrator._build_config_payload(cfg)
        assert payload["accessRules"] == [{"accessType": "READ"}]

    def test_build_payload_empty_access_rules_when_none(self):
        cfg = _make_app_cfg(access_rules=None)
        payload = self.migrator._build_config_payload(cfg)
        assert payload["accessRules"] == []

    # ── _create_config ─────────────────────────────────────────────────────────

    def test_create_config_returns_true_on_success(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = json.dumps({"id": "new-id"}).encode()
        api.add_application_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)
        cfg = _make_app_cfg("App A")

        result = self.migrator._create_config(api, cfg)

        assert result is True

    def test_create_config_returns_true_when_body_empty(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = b""
        api.add_application_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)
        cfg = _make_app_cfg("App A")

        result = self.migrator._create_config(api, cfg)

        assert result is True

    def test_create_config_returns_false_on_api_exception(self):
        api = MagicMock()
        exc = ApiException(status=409, reason="Conflict")
        exc.body = json.dumps({"message": "already exists"})
        api.add_application_config_without_preload_content.__wrapped__ = MagicMock(side_effect=exc)
        cfg = _make_app_cfg("App A")

        result = self.migrator._create_config(api, cfg)

        assert result is False

    def test_create_config_returns_false_on_generic_exception(self):
        api = MagicMock()
        api.add_application_config_without_preload_content.__wrapped__ = MagicMock(
            side_effect=RuntimeError("unexpected")
        )
        cfg = _make_app_cfg("App A")

        result = self.migrator._create_config(api, cfg)

        assert result is False

    # ── _update_config ─────────────────────────────────────────────────────────

    def test_update_config_returns_true_on_success(self):
        api = MagicMock()
        raw = MagicMock()
        raw.read.return_value = json.dumps({"id": "app-1"}).encode()
        api.put_application_config_without_preload_content.__wrapped__ = MagicMock(return_value=raw)

        src = _make_app_cfg("App A", cfg_id="src-1")
        tgt = _make_app_cfg("App A", cfg_id="app-1")

        result = self.migrator._update_config(api, src, [tgt])

        assert result is True

    def test_update_config_returns_false_when_target_not_found(self):
        api = MagicMock()
        # Give the __wrapped__ attribute a real Mock so we can assert on it later
        wrapped = MagicMock()
        api.put_application_config_without_preload_content.__wrapped__ = wrapped

        src = _make_app_cfg("App A")
        # target list has a different label
        other = _make_app_cfg("Other App", cfg_id="other-1")

        result = self.migrator._update_config(api, src, [other])

        assert result is False
        wrapped.assert_not_called()

    def test_update_config_returns_false_on_api_exception(self):
        api = MagicMock()
        exc = ApiException(status=400, reason="Bad Request")
        exc.body = json.dumps({"message": "invalid payload"})
        api.put_application_config_without_preload_content.__wrapped__ = MagicMock(side_effect=exc)

        src = _make_app_cfg("App A", cfg_id="src-1")
        tgt = _make_app_cfg("App A", cfg_id="app-1")

        result = self.migrator._update_config(api, src, [tgt])

        assert result is False

    # ── prompt_duplicate ───────────────────────────────────────────────────────

    @patch("utils.sys.stdin.isatty", return_value=False)
    def test_prompt_non_interactive_returns_skip(self, _):
        assert prompt_duplicate("Application config", "App A") == "skip"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="s")
    def test_prompt_interactive_s_returns_skip(self, _, __):
        assert prompt_duplicate("Application config", "App A") == "skip"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="u")
    def test_prompt_interactive_u_returns_update(self, _, __):
        assert prompt_duplicate("Application config", "App A") == "update"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="c")
    def test_prompt_interactive_c_returns_cancel(self, _, __):
        assert prompt_duplicate("Application config", "App A") == "cancel"

    @patch("utils.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", side_effect=["invalid", "u"])
    def test_prompt_retries_on_invalid_input(self, _, __):
        assert prompt_duplicate("Application config", "App A") == "update"

    # ── migrate() ─────────────────────────────────────────────────────────────

    @patch.object(ApplicationConfigMigrator, "_get_configs", return_value=None)
    def test_migrate_returns_zeros_when_source_fetch_fails(self, _):
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}

    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_returns_zeros_when_target_fetch_fails(self, mock_get):
        src_cfg = _make_app_cfg("App A")
        mock_get.side_effect = [[src_cfg], None]
        result = self.migrator.migrate()
        assert result["source"] == 1
        assert result["migrated"] == 0

    @patch.object(ApplicationConfigMigrator, "_create_config", return_value=True)
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_creates_new_config(self, mock_get, mock_create):
        src_cfg = _make_app_cfg("App A")
        mock_get.side_effect = [[src_cfg], []]
        result = self.migrator.migrate()
        mock_create.assert_called_once()
        assert result["migrated"] == 1
        assert result["skipped"] == 0

    @patch.object(ApplicationConfigMigrator, "_create_config", return_value=False)
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_counts_failed_create_as_skipped(self, mock_get, mock_create):
        src_cfg = _make_app_cfg("App A")
        mock_get.side_effect = [[src_cfg], []]
        result = self.migrator.migrate()
        assert result["migrated"] == 0
        assert result["skipped"] == 1

    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_skips_duplicate_when_on_duplicate_skip(self, mock_get):
        self.config.on_duplicate = "skip"
        src = _make_app_cfg("App A")
        tgt = _make_app_cfg("App A", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["skipped"] == 1
        assert result["migrated"] == 0

    @patch.object(ApplicationConfigMigrator, "_update_config", return_value=True)
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_updates_duplicate_when_on_duplicate_update(self, mock_get, mock_update):
        self.config.on_duplicate = "update"
        src = _make_app_cfg("App A")
        tgt = _make_app_cfg("App A", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        mock_update.assert_called_once()
        assert result["updated"] == 1
        assert result["migrated"] == 0

    @patch.object(ApplicationConfigMigrator, "_update_config", return_value=False)
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_failed_update_counted_as_skipped(self, mock_get, mock_update):
        self.config.on_duplicate = "update"
        src = _make_app_cfg("App A")
        tgt = _make_app_cfg("App A", cfg_id="tgt-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["updated"] == 0
        assert result["skipped"] == 1

    @patch.object(ApplicationConfigMigrator, "_create_config")
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_cancel_stops_loop(self, mock_get, mock_create):
        self.config.on_duplicate = "cancel"
        src1 = _make_app_cfg("App A")
        src2 = _make_app_cfg("App B")
        tgt1 = _make_app_cfg("App A", cfg_id="t1")
        tgt2 = _make_app_cfg("App B", cfg_id="t2")
        mock_get.side_effect = [[src1, src2], [tgt1, tgt2]]
        result = self.migrator.migrate()
        mock_create.assert_not_called()
        assert result["migrated"] == 0

    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_result_has_all_required_keys(self, mock_get):
        mock_get.side_effect = [[], []]
        result = self.migrator.migrate()
        for key in ("source", "migrated", "updated", "skipped"):
            assert key in result

    @patch.object(ApplicationConfigMigrator, "_create_config", return_value=True)
    @patch.object(ApplicationConfigMigrator, "_get_configs")
    def test_migrate_get_configs_called_exactly_twice(self, mock_get, _):
        """_get_configs is called once for source and once for target."""
        mock_get.side_effect = [
            [_make_app_cfg("A"), _make_app_cfg("B")],
            [],
        ]
        self.migrator.migrate()
        assert mock_get.call_count == 2
