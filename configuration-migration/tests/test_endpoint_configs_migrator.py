"""Unit tests for the EndpointConfigMigrator class."""

import json
import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "endpoint-configuration"))
from migrator import EndpointConfigMigrator
from config import Config


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_ep_cfg(service_id="svc-1", endpoint_case="ORIGINAL",
                 collected_path_rule=False, first_path_rule=False, rules=None):
    """Return a minimal EndpointConfig mock."""
    cfg = MagicMock()
    cfg.service_id = service_id
    cfg.endpoint_case = endpoint_case
    cfg.endpoint_name_by_collected_path_template_rule_enabled = collected_path_rule
    cfg.endpoint_name_by_first_path_segment_rule_enabled = first_path_rule
    cfg.rules = rules
    return cfg


def _raw_response(items: list) -> MagicMock:
    """Simulate the raw HTTP response returned by *_without_preload_content calls."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(items).encode()
    return mock


# ── tests ──────────────────────────────────────────────────────────────────────


class TestEndpointConfigMigrator:
    """Tests for EndpointConfigMigrator."""

    def setup_method(self):
        self.config = Config()
        self.config.source_token = "src-token"
        self.config.source_url = "https://source.example.com"
        self.config.target_token = "tgt-token"
        self.config.target_url = "https://target.example.com"
        self.config.verify_ssl = True
        self.config.on_duplicate = "ask"

        self.migrator = EndpointConfigMigrator(self.config)

    # ── __init__ ───────────────────────────────────────────────────────────────

    def test_init_stores_config(self):
        assert self.migrator.config is self.config

    @patch("migrator.urllib3.disable_warnings")
    def test_init_disables_ssl_warnings_when_verify_ssl_false(self, mock_dw):
        self.config.verify_ssl = False
        EndpointConfigMigrator(self.config)
        mock_dw.assert_called_once()

    @patch("migrator.urllib3.disable_warnings")
    def test_init_does_not_disable_ssl_warnings_when_verify_ssl_true(self, mock_dw):
        EndpointConfigMigrator(self.config)
        mock_dw.assert_not_called()

    # ── _get_configs ───────────────────────────────────────────────────────────

    @patch("migrator.EndpointConfig")
    def test_get_configs_success(self, mock_model):
        api = MagicMock()
        item = {"serviceId": "svc-1", "endpointCase": "ORIGINAL", "rules": None}
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_ep_cfg()

        result = self.migrator._get_configs(api, "source")

        assert result is not None
        assert len(result) == 1
        mock_model.from_dict.assert_called_once_with(item)

    @patch("migrator.EndpointConfig")
    def test_get_configs_defaults_null_endpoint_case_to_original(self, mock_model):
        """null endpointCase from legacy backends is defaulted to 'ORIGINAL'."""
        api = MagicMock()
        item = {"serviceId": "svc-1", "endpointCase": None}
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_ep_cfg()

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["endpointCase"] == "ORIGINAL"

    @patch("migrator.EndpointConfig")
    def test_get_configs_preserves_explicit_endpoint_case(self, mock_model):
        api = MagicMock()
        item = {"serviceId": "svc-1", "endpointCase": "LOWERCASE"}
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_ep_cfg(endpoint_case="LOWERCASE")

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["endpointCase"] == "LOWERCASE"

    @patch("migrator.EndpointConfig")
    def test_get_configs_normalises_empty_rules_to_none(self, mock_model):
        """Empty rules list from legacy backends is normalised to None."""
        api = MagicMock()
        item = {"serviceId": "svc-1", "endpointCase": "ORIGINAL", "rules": []}
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_ep_cfg()

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["rules"] is None

    @patch("migrator.EndpointConfig")
    def test_get_configs_preserves_non_empty_rules(self, mock_model):
        api = MagicMock()
        rule = {"type": "CONTAINS", "value": "/api"}
        item = {"serviceId": "svc-1", "endpointCase": "ORIGINAL", "rules": [rule]}
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([item])
        mock_model.from_dict.return_value = _make_ep_cfg(rules=[rule])

        self.migrator._get_configs(api, "source")

        called_item = mock_model.from_dict.call_args[0][0]
        assert called_item["rules"] == [rule]

    @patch("migrator.EndpointConfig")
    def test_get_configs_returns_empty_list_for_empty_response(self, mock_model):
        api = MagicMock()
        api.get_endpoint_configs_without_preload_content.return_value = _raw_response([])

        result = self.migrator._get_configs(api, "target")

        assert result == []

    def test_get_configs_returns_none_on_exception(self):
        api = MagicMock()
        api.get_endpoint_configs_without_preload_content.side_effect = Exception("timeout")

        result = self.migrator._get_configs(api, "source")

        assert result is None

    # ── _create_config ─────────────────────────────────────────────────────────

    def test_create_config_returns_true_on_success(self):
        api = MagicMock()
        result_mock = MagicMock()
        result_mock.service_id = "new-svc-1"
        api.create_endpoint_config.return_value = result_mock
        cfg = _make_ep_cfg("svc-1")

        result = self.migrator._create_config(api, cfg)

        assert result is True
        api.create_endpoint_config.assert_called_once()

    def test_create_config_builds_payload_with_source_fields(self):
        """The EndpointConfig payload passed to create uses source config values."""
        api = MagicMock()
        result_mock = MagicMock()
        result_mock.service_id = "new-svc-1"
        api.create_endpoint_config.return_value = result_mock

        # Use a valid enum value ("LOWER") and None rules to avoid pydantic validation errors
        cfg = _make_ep_cfg("svc-1", endpoint_case="LOWER",
                           collected_path_rule=True, first_path_rule=False, rules=None)

        self.migrator._create_config(api, cfg)

        payload = api.create_endpoint_config.call_args[0][0]
        assert payload.service_id == "svc-1"
        assert payload.endpoint_case == "LOWER"
        assert payload.endpoint_name_by_collected_path_template_rule_enabled is True
        assert payload.endpoint_name_by_first_path_segment_rule_enabled is False
        assert payload.rules is None

    def test_create_config_returns_false_on_exception(self):
        api = MagicMock()
        api.create_endpoint_config.side_effect = Exception("network error")
        cfg = _make_ep_cfg("svc-1")

        assert self.migrator._create_config(api, cfg) is False

    # ── _update_config ─────────────────────────────────────────────────────────

    def test_update_config_returns_true_on_success(self):
        api = MagicMock()
        result_mock = MagicMock()
        result_mock.service_id = "tgt-svc-1"
        api.update_endpoint_config.return_value = result_mock

        src = _make_ep_cfg("src-svc-1")
        tgt = _make_ep_cfg("tgt-svc-1")

        result = self.migrator._update_config(api, src, tgt)

        assert result is True

    def test_update_config_uses_target_service_id(self):
        """The update call uses the target's service ID, not the source's."""
        api = MagicMock()
        result_mock = MagicMock()
        result_mock.service_id = "tgt-svc-1"
        api.update_endpoint_config.return_value = result_mock

        src = _make_ep_cfg("src-svc-99")
        tgt = _make_ep_cfg("tgt-svc-1")

        self.migrator._update_config(api, src, tgt)

        call_args = api.update_endpoint_config.call_args
        # First positional arg is the service_id to update
        assert call_args[0][0] == "tgt-svc-1"
        # The payload's serviceId should also be the target's
        payload = call_args[0][1]
        assert payload.service_id == "tgt-svc-1"

    def test_update_config_copies_source_settings_to_payload(self):
        api = MagicMock()
        result_mock = MagicMock()
        result_mock.service_id = "tgt-svc-1"
        api.update_endpoint_config.return_value = result_mock

        # Use valid enum value ("UPPER") and None rules to avoid pydantic validation errors
        src = _make_ep_cfg("src-svc-1", endpoint_case="UPPER",
                           collected_path_rule=True, first_path_rule=True, rules=None)
        tgt = _make_ep_cfg("tgt-svc-1")

        self.migrator._update_config(api, src, tgt)

        payload = api.update_endpoint_config.call_args[0][1]
        assert payload.endpoint_case == "UPPER"
        assert payload.endpoint_name_by_collected_path_template_rule_enabled is True
        assert payload.endpoint_name_by_first_path_segment_rule_enabled is True
        assert payload.rules is None

    def test_update_config_returns_false_on_exception(self):
        api = MagicMock()
        api.update_endpoint_config.side_effect = Exception("server error")

        src = _make_ep_cfg("src-svc-1")
        tgt = _make_ep_cfg("tgt-svc-1")

        assert self.migrator._update_config(api, src, tgt) is False

    # ── _prompt_duplicate ──────────────────────────────────────────────────────

    @patch("migrator.sys.stdin.isatty", return_value=False)
    def test_prompt_non_interactive_returns_skip(self, _):
        assert self.migrator._prompt_duplicate("svc-1") == "skip"

    @patch("migrator.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="s")
    def test_prompt_interactive_s_returns_skip(self, _, __):
        assert self.migrator._prompt_duplicate("svc-1") == "skip"

    @patch("migrator.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="u")
    def test_prompt_interactive_u_returns_update(self, _, __):
        assert self.migrator._prompt_duplicate("svc-1") == "update"

    @patch("migrator.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", return_value="c")
    def test_prompt_interactive_c_returns_cancel(self, _, __):
        assert self.migrator._prompt_duplicate("svc-1") == "cancel"

    @patch("migrator.sys.stdin.isatty", return_value=True)
    @patch("builtins.input", side_effect=["nope", "cancel"])
    def test_prompt_retries_on_invalid_then_accepts_full_word(self, _, __):
        assert self.migrator._prompt_duplicate("svc-1") == "cancel"

    # ── migrate() ─────────────────────────────────────────────────────────────

    @patch.object(EndpointConfigMigrator, "_get_configs", return_value=None)
    def test_migrate_returns_zeros_when_source_fetch_fails(self, _):
        result = self.migrator.migrate()
        assert result == {"source": 0, "migrated": 0, "updated": 0, "skipped": 0}

    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_returns_zeros_when_target_fetch_fails(self, mock_get):
        src = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], None]
        result = self.migrator.migrate()
        assert result["source"] == 1
        assert result["migrated"] == 0

    @patch.object(EndpointConfigMigrator, "_create_config", return_value=True)
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_creates_new_config(self, mock_get, mock_create):
        src = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], []]
        result = self.migrator.migrate()
        mock_create.assert_called_once()
        assert result["migrated"] == 1
        assert result["skipped"] == 0

    @patch.object(EndpointConfigMigrator, "_create_config", return_value=False)
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_counts_failed_create_as_skipped(self, mock_get, _):
        src = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], []]
        result = self.migrator.migrate()
        assert result["migrated"] == 0
        assert result["skipped"] == 1

    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_skips_duplicate_when_on_duplicate_skip(self, mock_get):
        self.config.on_duplicate = "skip"
        src = _make_ep_cfg("svc-1")
        tgt = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["skipped"] == 1
        assert result["migrated"] == 0

    @patch.object(EndpointConfigMigrator, "_update_config", return_value=True)
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_updates_duplicate_when_on_duplicate_update(self, mock_get, mock_update):
        self.config.on_duplicate = "update"
        src = _make_ep_cfg("svc-1")
        tgt = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        # Verify src and tgt were passed; the first arg is the live API object so skip it
        assert mock_update.call_count == 1
        _, call_src, call_tgt = mock_update.call_args[0]
        assert call_src is src
        assert call_tgt is tgt
        assert result["updated"] == 1
        assert result["migrated"] == 0

    @patch.object(EndpointConfigMigrator, "_update_config", return_value=False)
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_failed_update_counted_as_skipped(self, mock_get, _):
        self.config.on_duplicate = "update"
        src = _make_ep_cfg("svc-1")
        tgt = _make_ep_cfg("svc-1")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["updated"] == 0
        assert result["skipped"] == 1

    @patch.object(EndpointConfigMigrator, "_create_config")
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_cancel_stops_loop(self, mock_get, mock_create):
        self.config.on_duplicate = "cancel"
        src1 = _make_ep_cfg("svc-1")
        src2 = _make_ep_cfg("svc-2")
        tgt1 = _make_ep_cfg("svc-1")
        tgt2 = _make_ep_cfg("svc-2")
        mock_get.side_effect = [[src1, src2], [tgt1, tgt2]]
        result = self.migrator.migrate()
        mock_create.assert_not_called()
        assert result["migrated"] == 0

    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_deduplication_keyed_on_service_id(self, mock_get):
        """Configs with the same serviceId are treated as duplicates regardless of other fields."""
        self.config.on_duplicate = "skip"
        # Both share service_id "svc-1"
        src = _make_ep_cfg("svc-1", endpoint_case="LOWERCASE")
        tgt = _make_ep_cfg("svc-1", endpoint_case="ORIGINAL")
        mock_get.side_effect = [[src], [tgt]]
        result = self.migrator.migrate()
        assert result["skipped"] == 1
        assert result["migrated"] == 0

    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_result_has_all_required_keys(self, mock_get):
        mock_get.side_effect = [[], []]
        result = self.migrator.migrate()
        for key in ("source", "migrated", "updated", "skipped"):
            assert key in result

    @patch.object(EndpointConfigMigrator, "_create_config", return_value=True)
    @patch.object(EndpointConfigMigrator, "_get_configs")
    def test_migrate_get_configs_called_exactly_twice(self, mock_get, _):
        mock_get.side_effect = [
            [_make_ep_cfg("svc-1"), _make_ep_cfg("svc-2")],
            [],
        ]
        self.migrator.migrate()
        assert mock_get.call_count == 2
