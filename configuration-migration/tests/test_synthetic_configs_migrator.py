"""Unit tests for the SyntheticConfigMigrator class."""

import json
import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest
import importlib.util

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
_syn_dir = os.path.join(os.path.dirname(__file__), "..", "synthetic-configs")
_spec = importlib.util.spec_from_file_location("syn_migrator", os.path.join(_syn_dir, "migrator.py"))
_syn_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_syn_module)
sys.modules["syn_migrator"] = _syn_module
SyntheticConfigMigrator = _syn_module.SyntheticConfigMigrator

from config import Config
from utils import empty_result, make_result, partial_result


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_config(**kwargs):
    """Return a minimal Config with required fields set."""
    cfg = Config()
    cfg.source_token = "src-token"
    cfg.source_url = "https://source.example.com"
    cfg.target_token = "tgt-token"
    cfg.target_url = "https://target.example.com"
    cfg.verify_ssl = True
    cfg.on_duplicate = "ask"
    cfg.dry_run = False
    cfg.events_source = "api"
    cfg.events_file_path = "source_synthetic_configs.json"
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


def _make_test(label="My Test", test_id="test-1"):
    """Return a minimal synthetic test dict."""
    return {"id": test_id, "label": label, "active": True}


# ── class-name / import sanity ──────────────────────────────────────────────────


class TestClassImport:
    def test_class_is_importable_as_synthetic_config_migrator(self):
        assert SyntheticConfigMigrator is not None

    def test_class_name(self):
        assert SyntheticConfigMigrator.__name__ == "SyntheticConfigMigrator"


# ── migrate() — dry_run guard ───────────────────────────────────────────────────


class TestMigrateDryRunGuard:
    def test_dry_run_flag_routes_to_dry_run_method(self):
        cfg = _make_config(dry_run=True)
        m = SyntheticConfigMigrator(cfg)
        dry_result = make_result(source=2, migrated=1, updated=1, skipped=0)
        with patch.object(m, "_dry_run", return_value=dry_result) as mock_dry:
            result = m.migrate()
        mock_dry.assert_called_once()
        assert result == dry_result

    def test_dry_run_does_not_call_check_permissions(self):
        cfg = _make_config(dry_run=True)
        m = SyntheticConfigMigrator(cfg)
        with patch.object(m, "_dry_run", return_value=empty_result()):
            with patch(_syn_module.__name__ + ".check_permissions") as mock_perm:
                m.migrate()
        mock_perm.assert_not_called()


# ── migrate() — permission check ───────────────────────────────────────────────


class TestMigratePermissions:
    def test_permission_failure_returns_empty_result(self):
        cfg = _make_config()
        m = SyntheticConfigMigrator(cfg)
        with patch(_syn_module.__name__ + ".check_permissions", return_value=False):
            result = m.migrate()
        assert result == empty_result()

    def test_permission_success_proceeds_to_source_fetch(self):
        cfg = _make_config()
        m = SyntheticConfigMigrator(cfg)
        with patch(_syn_module.__name__ + ".check_permissions", return_value=True):
            with patch.object(m, "_get_source_synthetic_test_config", return_value=None):
                result = m.migrate()
        # source fetch returned None → empty_result
        assert result == empty_result()


# ── migrate() — counts and MigrationResult shape ───────────────────────────────


class TestMigrateCounts:
    def setup_method(self):
        self.cfg = _make_config()
        self.m = SyntheticConfigMigrator(self.cfg)

    def _run(self, source, target, single_test_results):
        """Helper: patch permissions/fetch and _migrate_single_test, run migrate()."""
        with patch(_syn_module.__name__ + ".check_permissions", return_value=True):
            with patch.object(self.m, "_get_source_synthetic_test_config", return_value=source):
                with patch.object(self.m, "_get_target_synthetic_test_config", return_value=target):
                    with patch.object(self.m, "_migrate_single_test", side_effect=single_test_results):
                        return self.m.migrate()

    def test_all_created(self):
        source = [_make_test("A", "id-1"), _make_test("B", "id-2")]
        target = []
        results = [("migrated", "new-1"), ("migrated", "new-2")]
        r = self._run(source, target, results)
        assert r["source"] == 2
        assert r["migrated"] == 2
        assert r["updated"] == 0
        assert r["skipped"] == 0
        assert r["failed"] == 0

    def test_failed_increments_failed_count(self):
        source = [_make_test("A", "id-1"), _make_test("B", "id-2")]
        target = []
        results = [("migrated", "new-1"), ("failed", None)]
        r = self._run(source, target, results)
        assert r["migrated"] == 1
        assert r["failed"] == 1

    def test_skipped_increments_skipped_count(self):
        source = [_make_test("A", "id-1")]
        target = [_make_test("A", "tgt-1")]
        results = [("skipped", None)]
        r = self._run(source, target, results)
        assert r["skipped"] == 1
        assert r["migrated"] == 0

    def test_updated_increments_updated_count(self):
        source = [_make_test("A", "id-1")]
        target = [_make_test("A", "tgt-1")]
        results = [("updated", None)]
        r = self._run(source, target, results)
        assert r["updated"] == 1

    def test_cancelled_breaks_loop(self):
        source = [_make_test("A", "id-1"), _make_test("B", "id-2")]
        target = []
        # First test cancelled, second should never be processed
        results = [("cancelled", None)]
        r = self._run(source, target, results)
        assert r["migrated"] == 0

    def test_result_has_no_synthetic_test_mapping_key(self):
        source = [_make_test("A", "id-1")]
        target = []
        r = self._run(source, target, [("migrated", "new-1")])
        assert "synthetic_test_mapping" not in r

    def test_result_has_all_required_keys(self):
        source = []
        target = []
        with patch(_syn_module.__name__ + ".check_permissions", return_value=True):
            with patch.object(self.m, "_get_source_synthetic_test_config", return_value=source):
                with patch.object(self.m, "_get_target_synthetic_test_config", return_value=target):
                    r = self.m.migrate()
        for key in ("source", "migrated", "updated", "skipped", "failed"):
            assert key in r

    def test_target_fetch_failure_returns_partial_result(self):
        source = [_make_test("A", "id-1")]
        with patch(_syn_module.__name__ + ".check_permissions", return_value=True):
            with patch.object(self.m, "_get_source_synthetic_test_config", return_value=source):
                with patch.object(self.m, "_get_target_synthetic_test_config", return_value=None):
                    r = self.m.migrate()
        assert r["source"] == 1
        assert r["migrated"] == 0


# ── _dry_run() ──────────────────────────────────────────────────────────────────


class TestDryRun:
    def setup_method(self):
        self.cfg = _make_config(dry_run=True)
        self.m = SyntheticConfigMigrator(self.cfg)

    def _run_dry(self, source, target):
        with patch(
            _syn_module.__name__ + ".dry_run_connectivity_check",
            return_value=(source, target),
        ):
            with patch(_syn_module.__name__ + ".print_dry_run_preview"):
                return self.m._dry_run()

    def test_dry_run_returns_would_create_count(self):
        source = [_make_test("New A", "s-1"), _make_test("New B", "s-2")]
        target = []
        r = self._run_dry(source, target)
        assert r["migrated"] == 2
        assert r["updated"] == 0

    def test_dry_run_returns_would_update_count(self):
        source = [_make_test("Existing", "s-1")]
        target = [_make_test("Existing", "t-1")]
        r = self._run_dry(source, target)
        assert r["updated"] == 1
        assert r["migrated"] == 0

    def test_dry_run_skips_tests_with_no_label(self):
        source = [{"id": "s-1", "active": True}]  # no 'label' key
        target = []
        r = self._run_dry(source, target)
        assert r["skipped"] == 1
        assert r["skipped_invalid"] == 1
        assert r["migrated"] == 0

    def test_dry_run_aborted_returns_empty_result(self):
        from permissions import DryRunAbortedError
        with patch(
            _syn_module.__name__ + ".dry_run_connectivity_check",
            side_effect=DryRunAbortedError("fail"),
        ):
            r = self.m._dry_run()
        assert r == empty_result()

    def test_dry_run_makes_no_api_writes(self):
        source = [_make_test("A", "s-1")]
        target = []
        with patch(
            _syn_module.__name__ + ".dry_run_connectivity_check",
            return_value=(source, target),
        ):
            with patch(_syn_module.__name__ + ".print_dry_run_preview"):
                with patch.object(self.m, "_create_synthetic_test_config") as mock_create:
                    with patch.object(self.m, "_update_synthetic_test_config") as mock_update:
                        self.m._dry_run()
        mock_create.assert_not_called()
        mock_update.assert_not_called()


# ── _migrate_single_test() ──────────────────────────────────────────────────────


class TestMigrateSingleTest:
    def setup_method(self):
        self.cfg = _make_config()
        self.m = SyntheticConfigMigrator(self.cfg)

    def test_missing_label_returns_skipped(self):
        test = {"id": "s-1"}  # no label
        status, new_id = self.m._migrate_single_test(test, {})
        assert status == "skipped"
        assert new_id is None

    def test_missing_id_returns_skipped(self):
        test = {"label": "My Test"}  # no id
        status, new_id = self.m._migrate_single_test(test, {})
        assert status == "skipped"
        assert new_id is None

    def test_new_test_successful_create(self):
        test = _make_test("New", "s-1")
        with patch.object(self.m, "_create_synthetic_test_config", return_value="tgt-new"):
            status, new_id = self.m._migrate_single_test(test, {})
        assert status == "migrated"
        assert new_id == "tgt-new"

    def test_new_test_failed_create_returns_failed(self):
        test = _make_test("New", "s-1")
        with patch.object(self.m, "_create_synthetic_test_config", return_value=None):
            status, new_id = self.m._migrate_single_test(test, {})
        assert status == "failed"
        assert new_id is None

    def test_duplicate_user_skips(self):
        test = _make_test("Dup", "s-1")
        mapping = {"s-1": "t-1"}
        with patch(_syn_module.__name__ + ".prompt_duplicate", return_value="skip"):
            status, _ = self.m._migrate_single_test(test, mapping)
        assert status == "skipped"

    def test_duplicate_user_updates_success(self):
        test = _make_test("Dup", "s-1")
        mapping = {"s-1": "t-1"}
        with patch(_syn_module.__name__ + ".prompt_duplicate", return_value="update"):
            with patch.object(self.m, "_update_synthetic_test_config", return_value="updated"):
                status, _ = self.m._migrate_single_test(test, mapping)
        assert status == "updated"

    def test_duplicate_user_updates_failure_returns_failed(self):
        test = _make_test("Dup", "s-1")
        mapping = {"s-1": "t-1"}
        with patch(_syn_module.__name__ + ".prompt_duplicate", return_value="update"):
            with patch.object(self.m, "_update_synthetic_test_config", return_value="failed"):
                status, _ = self.m._migrate_single_test(test, mapping)
        assert status == "failed"

    def test_duplicate_user_cancels(self):
        test = _make_test("Dup", "s-1")
        mapping = {"s-1": "t-1"}
        with patch(_syn_module.__name__ + ".prompt_duplicate", return_value="cancel"):
            status, _ = self.m._migrate_single_test(test, mapping)
        assert status == "cancelled"
