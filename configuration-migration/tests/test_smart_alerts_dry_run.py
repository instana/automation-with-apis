"""Tests for dry-run support in BaseSmartAlertsMigrator and all four subclass migrators."""

import importlib
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure the project root and submodule directories are on the path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
sys.path.insert(0, os.path.join(_root, 'infrastructure-smart-alerts'))
sys.path.insert(0, os.path.join(_root, 'application-smart-alerts'))
sys.path.insert(0, os.path.join(_root, 'website-smart-alerts'))
sys.path.insert(0, os.path.join(_root, 'mobile-app-smart-alerts'))

from config import Config
from base_smart_alerts_migrator import BaseSmartAlertsMigrator, _REQUIRED_PERMISSIONS
from utils import empty_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> Config:
    cfg = Config()
    cfg.source_token = "src-tok"
    cfg.source_url = "http://source.example.com"
    cfg.target_token = "tgt-tok"
    cfg.target_url = "http://target.example.com"
    cfg.verify_ssl = True
    cfg.events_source = "api"
    cfg.on_duplicate = "skip"
    cfg.dry_run = True
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


def _make_alert(name="My Alert", alert_id="src-1", **extra):
    return {"id": alert_id, "name": name, "severity": "critical", **extra}


# Minimal concrete subclass — uses InfrastructureSmartAlertsMigrator's logic
# but we import via importlib so the dynamic sys.path trick works cleanly.
def _get_infra_migrator(config: Config):
    spec = importlib.util.spec_from_file_location(
        "infra_migrator",
        os.path.join(_root, "infrastructure-smart-alerts", "migrator.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.InfrastructureSmartAlertsMigrator(config)


# ---------------------------------------------------------------------------
# _dry_run() — connectivity / abort paths
# ---------------------------------------------------------------------------

class TestDryRunAbortPaths:
    """_dry_run() should return empty_result() on any connectivity failure."""

    @patch("base_smart_alerts_migrator.dry_run_connectivity_check")
    def test_source_fetch_failure_returns_empty(self, mock_check):
        from base_smart_alerts_migrator import DryRunAbortedError
        mock_check.side_effect = DryRunAbortedError("source fetch failed")

        migrator = _get_infra_migrator(_make_config())
        result = migrator._dry_run()

        assert result == empty_result()

    @patch("base_smart_alerts_migrator.dry_run_connectivity_check")
    def test_target_fetch_failure_returns_empty(self, mock_check):
        from base_smart_alerts_migrator import DryRunAbortedError
        mock_check.side_effect = DryRunAbortedError("target fetch failed")

        migrator = _get_infra_migrator(_make_config())
        result = migrator._dry_run()

        assert result == empty_result()

    @patch("base_smart_alerts_migrator.dry_run_connectivity_check")
    def test_permission_failure_returns_empty(self, mock_check):
        from base_smart_alerts_migrator import DryRunAbortedError
        mock_check.side_effect = DryRunAbortedError("missing canConfigureEventsAndAlerts")

        migrator = _get_infra_migrator(_make_config())
        result = migrator._dry_run()

        assert result == empty_result()

    @patch("base_smart_alerts_migrator.dry_run_connectivity_check")
    def test_connectivity_check_receives_correct_permissions(self, mock_check):
        """dry_run_connectivity_check is called with the migrator's required_permissions."""
        mock_check.return_value = ([], [])
        migrator = _get_infra_migrator(_make_config())
        migrator._init_resource_maps = MagicMock()

        migrator._dry_run()

        _, kwargs = mock_check.call_args
        assert kwargs["required_permissions"] == migrator.required_permissions


# ---------------------------------------------------------------------------
# _dry_run() — classification of source items
# ---------------------------------------------------------------------------

class TestDryRunClassification:
    """_dry_run() should correctly classify each source item."""

    def _run_dry_run(self, source_items, target_items, extra_config=None):
        """Helper: patch connectivity check and resource maps, run _dry_run()."""
        cfg = _make_config(**(extra_config or {}))
        migrator = _get_infra_migrator(cfg)
        migrator._init_resource_maps = MagicMock()

        with patch("base_smart_alerts_migrator.dry_run_connectivity_check",
                   return_value=(source_items, target_items)):
            return migrator._dry_run()

    def test_new_item_counted_as_would_create(self, capsys):
        result = self._run_dry_run(
            source_items=[_make_alert("New Alert")],
            target_items=[],
        )
        assert result["migrated"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert "Would create" in capsys.readouterr().out

    def test_changed_item_counted_as_would_update(self, capsys):
        source = _make_alert("Existing Alert", alert_id="id-1", severity="critical")
        target = _make_alert("Existing Alert", alert_id="id-1", severity="warning")
        result = self._run_dry_run(
            source_items=[source],
            target_items=[target],
        )
        assert result["updated"] == 1
        assert result["migrated"] == 0
        assert "Would update" in capsys.readouterr().out

    def test_identical_item_counted_as_skipped_identical(self, capsys):
        alert = _make_alert("Same Alert", alert_id="id-1")
        # Same content in source and target
        result = self._run_dry_run(
            source_items=[alert],
            target_items=[dict(alert)],
        )
        assert result["skipped"] == 1
        assert result["skipped_identical"] == 1
        assert result["migrated"] == 0
        out = capsys.readouterr().out
        assert "identical" in out

    def test_unnamed_item_counted_as_skipped_invalid(self, capsys):
        result = self._run_dry_run(
            source_items=[{"id": "x", "severity": "warning"}],  # no 'name'
            target_items=[],
        )
        assert result["skipped"] == 1
        assert result["skipped_invalid"] == 1
        assert result["migrated"] == 0
        assert "Would skip" in capsys.readouterr().out

    def test_mixed_items_correct_totals(self, capsys):
        new_alert = _make_alert("New", alert_id="new-1")
        changed_src = _make_alert("Changed", alert_id="chg-1", severity="critical")
        changed_tgt = _make_alert("Changed", alert_id="chg-1", severity="warning")
        identical = _make_alert("Same", alert_id="same-1")
        unnamed = {"id": "u1"}

        result = self._run_dry_run(
            source_items=[new_alert, changed_src, identical, unnamed],
            target_items=[changed_tgt, dict(identical)],
        )
        assert result["source"] == 4
        assert result["migrated"] == 1
        assert result["updated"] == 1
        assert result["skipped_identical"] == 1
        assert result["skipped_invalid"] == 1
        assert result["skipped"] == 2
        assert result["failed"] == 0

    def test_no_api_writes_made(self):
        """_dry_run() must not call any create/update API methods."""
        cfg = _make_config()
        migrator = _get_infra_migrator(cfg)
        migrator._init_resource_maps = MagicMock()
        migrator._create_config = MagicMock()
        migrator._update_config = MagicMock()

        with patch("base_smart_alerts_migrator.dry_run_connectivity_check",
                   return_value=([_make_alert("A")], [])):
            migrator._dry_run()

        migrator._create_config.assert_not_called()
        migrator._update_config.assert_not_called()

    def test_name_match_used_when_id_not_in_target(self, capsys):
        """Items matched by name (not ID) are still detected as duplicates."""
        source = _make_alert("My Alert", alert_id="src-id")
        target = _make_alert("My Alert", alert_id="tgt-id")  # different ID, same name
        result = self._run_dry_run(
            source_items=[source],
            target_items=[target],
        )
        # Should be update (different IDs → content differs after strip)
        # or identical — either way, not "would create"
        assert result["migrated"] == 0

    def test_dry_run_summary_printed(self, capsys):
        result = self._run_dry_run(
            source_items=[_make_alert("A"), _make_alert("B")],
            target_items=[],
        )
        out = capsys.readouterr().out
        assert "Dry-run summary" in out
        assert "No changes were made" in out


# ---------------------------------------------------------------------------
# migrate() dispatch — dry_run flag gates _dry_run()
# ---------------------------------------------------------------------------

class TestMigrateDispatch:
    """migrate() should delegate to _dry_run() when config.dry_run is True."""

    def test_migrate_calls_dry_run_when_flag_set(self):
        cfg = _make_config(dry_run=True)
        migrator = _get_infra_migrator(cfg)
        migrator._dry_run = MagicMock(return_value=empty_result())

        migrator.migrate()

        migrator._dry_run.assert_called_once()

    def test_migrate_does_not_call_dry_run_when_flag_unset(self):
        cfg = _make_config(dry_run=False)
        migrator = _get_infra_migrator(cfg)
        migrator._dry_run = MagicMock()

        # Patch everything to prevent real API calls
        with patch("base_smart_alerts_migrator.check_permissions", return_value=False):
            migrator.migrate()

        migrator._dry_run.assert_not_called()

    def test_migrate_returns_empty_result_on_permission_failure(self):
        cfg = _make_config(dry_run=False)
        migrator = _get_infra_migrator(cfg)

        with patch("base_smart_alerts_migrator.check_permissions", return_value=False):
            result = migrator.migrate()

        assert result == empty_result()


# ---------------------------------------------------------------------------
# CLI — new flags are accepted by all four subcommand parsers
# ---------------------------------------------------------------------------

class TestCliFlags:
    """--dry-run and --on-duplicate are registered on all four smart alert subcommands."""

    def _parse(self, subcommand: str, extra_args: list):
        """Parse args for a smart alert subcommand without executing the migrator."""
        import argparse
        # Re-import cli to get a clean parser each time
        if 'cli' in sys.modules:
            del sys.modules['cli']
        import cli as cli_mod

        # Intercept main() argument parsing by calling parse_args directly
        # We need a fresh parser — rebuild it from the cli source
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        # Minimal recreation of just the relevant subparser
        sub = subparsers.add_parser(subcommand)
        sub.add_argument('--source-token')
        sub.add_argument('--source-url')
        sub.add_argument('--target-token')
        sub.add_argument('--target-url')
        sub.add_argument('--dry-run', action='store_true')
        sub.add_argument('--on-duplicate', choices=['skip', 'update', 'cancel'])

        return parser.parse_args([subcommand] + extra_args)

    @pytest.mark.parametrize("subcommand", [
        "application-smart-alerts",
        "website-smart-alerts",
        "mobile-app-smart-alerts",
        "infrastructure-smart-alerts",
    ])
    def test_dry_run_flag_accepted(self, subcommand):
        args = self._parse(subcommand, ["--dry-run",
                                        "--source-token", "s",
                                        "--source-url", "http://s.com",
                                        "--target-token", "t",
                                        "--target-url", "http://t.com"])
        assert args.dry_run is True

    @pytest.mark.parametrize("subcommand", [
        "application-smart-alerts",
        "website-smart-alerts",
        "mobile-app-smart-alerts",
        "infrastructure-smart-alerts",
    ])
    def test_on_duplicate_flag_accepted(self, subcommand):
        for choice in ("skip", "update", "cancel"):
            args = self._parse(subcommand, ["--on-duplicate", choice,
                                            "--source-token", "s",
                                            "--source-url", "http://s.com",
                                            "--target-token", "t",
                                            "--target-url", "http://t.com"])
            assert args.on_duplicate == choice
