"""Tests for CustomDashboardsMigratorAsync."""

import asyncio
import copy
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom-dashboards'))

from config import Config
from migrator_async import CustomDashboardsMigratorAsync


def _make_config(**kwargs) -> Config:
    cfg = Config()
    cfg.source_token = "src-token"
    cfg.source_url = "http://source.example.com"
    cfg.target_token = "tgt-token"
    cfg.target_url = "http://target.example.com"
    cfg.on_duplicate = "skip"
    cfg.events_source = "api"
    cfg.events_file_path = "dashboards.json"
    cfg.default_owner_id = None
    for k, v in kwargs.items():
        setattr(cfg, k, v)
    return cfg


def _make_dashboard(title="My Dashboard", owner_id=None, widgets=None):
    d = {
        "id": "src-id-1",
        "title": title,
        "widgets": widgets or [{"id": "w1", "width": 2, "height": 2, "config": {}}],
    }
    if owner_id:
        d["ownerId"] = owner_id
    return d


class TestPreparedDashboard(unittest.TestCase):
    """Unit tests for _prepare_dashboard (no I/O)."""

    def setUp(self):
        # asyncio.Semaphore requires a running loop on Python 3.9; provide one.
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.migrator = CustomDashboardsMigratorAsync(_make_config())

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    # Bug 5: must not mutate the original dict
    def test_does_not_mutate_source(self):
        original = _make_dashboard(owner_id="src-user")
        before = copy.deepcopy(original)
        self.migrator._prepare_dashboard(original, {})
        self.assertEqual(original, before, "Source dashboard should not be mutated")

    # Bug 2: ownerId is remapped when a mapping exists
    def test_owner_id_remapped_when_mapping_exists(self):
        dash = _make_dashboard(owner_id="src-user")
        result = self.migrator._prepare_dashboard(dash, {"src-user": "tgt-user"})
        self.assertEqual(result["ownerId"], "tgt-user")

    # Bug 2: ownerId falls back to default_owner_id
    def test_owner_id_falls_back_to_default(self):
        cfg = _make_config(default_owner_id="default-owner")
        migrator = CustomDashboardsMigratorAsync(cfg)
        dash = _make_dashboard(owner_id="src-user")
        result = migrator._prepare_dashboard(dash, {})  # no mapping
        self.assertEqual(result["ownerId"], "default-owner")

    # Bug 2: ownerId is dropped when no mapping and no default
    def test_owner_id_deleted_when_no_mapping_and_no_default(self):
        dash = _make_dashboard(owner_id="src-user")
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertNotIn("ownerId", result)

    def test_owner_field_removed(self):
        dash = _make_dashboard()
        dash["owner"] = {"name": "Alice"}
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertNotIn("owner", result)

    def test_access_rules_set(self):
        dash = _make_dashboard()
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertEqual(result["accessRules"], [{
            "accessType": "READ_WRITE",
            "relationType": "GLOBAL",
            "relatedId": "",
        }])

    def test_returns_none_for_no_title(self):
        dash = {"id": "x", "widgets": [{"id": "w1", "width": 1, "height": 1, "config": {}}]}
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertIsNone(result)

    def test_returns_none_for_no_widgets(self):
        dash = _make_dashboard()
        dash["widgets"] = []
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertIsNone(result)

    def test_returns_none_for_missing_widget_fields(self):
        dash = _make_dashboard(widgets=[{"id": "w1"}])  # missing width/height/config
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertIsNone(result)

    def test_valid_dashboard_returned(self):
        dash = _make_dashboard()
        result = self.migrator._prepare_dashboard(dash, {})
        self.assertIsNotNone(result)
        self.assertEqual(result["title"], "My Dashboard")


class TestMapUsers(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.migrator = CustomDashboardsMigratorAsync(_make_config())

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_maps_by_email(self):
        src = [{"id": "s1", "email": "a@x.com"}]
        tgt = [{"id": "t1", "email": "a@x.com"}]
        self.assertEqual(self.migrator._map_users(src, tgt), {"s1": "t1"})

    def test_ignores_unmatched_emails(self):
        src = [{"id": "s1", "email": "a@x.com"}]
        tgt = [{"id": "t2", "email": "b@x.com"}]
        self.assertEqual(self.migrator._map_users(src, tgt), {})

    def test_empty_inputs(self):
        self.assertEqual(self.migrator._map_users([], []), {})


class TestPromptForOverrideStrategy(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.migrator = CustomDashboardsMigratorAsync(_make_config())

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_config_update_returns_true(self):
        self.migrator.config.on_duplicate = "update"
        self.assertTrue(self.migrator._prompt_for_override_strategy())

    def test_config_skip_returns_false(self):
        self.migrator.config.on_duplicate = "skip"
        self.assertFalse(self.migrator._prompt_for_override_strategy())

    # Bug 7: cancel must return False, not call sys.exit
    def test_cancel_returns_false_not_sys_exit(self):
        self.migrator.config.on_duplicate = "ask"
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", side_effect=["c"]):
                result = self.migrator._prompt_for_override_strategy()
        self.assertFalse(result)

    def test_non_interactive_returns_false(self):
        self.migrator.config.on_duplicate = "ask"
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = self.migrator._prompt_for_override_strategy()
        self.assertFalse(result)


class TestGetSourceDashboardsFromFile(unittest.TestCase):
    """Bug 8: file-source mode must be implemented."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.migrator = CustomDashboardsMigratorAsync(_make_config(events_file_path="test.json"))

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_loads_valid_file(self):
        dashboards = [{"id": "1", "title": "D1"}, {"id": "2", "title": "D2"}]
        m = mock_open(read_data=json.dumps(dashboards))
        with patch("builtins.open", m):
            result = self.migrator._get_source_dashboards_from_file()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "D1")

    def test_returns_none_on_missing_file(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            result = self.migrator._get_source_dashboards_from_file()
        self.assertIsNone(result)

    def test_returns_none_on_invalid_json(self):
        m = mock_open(read_data="not valid json {{{")
        with patch("builtins.open", m):
            result = self.migrator._get_source_dashboards_from_file()
        self.assertIsNone(result)

    def test_returns_none_when_not_a_list(self):
        m = mock_open(read_data=json.dumps({"id": "1"}))
        with patch("builtins.open", m):
            result = self.migrator._get_source_dashboards_from_file()
        self.assertIsNone(result)


class TestCreateOrUpdateDashboardAsync(unittest.IsolatedAsyncioTestCase):
    """Unit tests for _create_or_update_dashboard_async."""

    def _make_migrator(self, **kwargs):
        return CustomDashboardsMigratorAsync(_make_config(**kwargs))

    def _make_mock_client(self):
        client = MagicMock()
        return client

    def _mock_response(self, status=200, json_data=None):
        resp = AsyncMock()
        resp.status = status
        resp.raise_for_status = MagicMock()
        resp.json = AsyncMock(return_value=json_data or {})
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        return resp

    # Bug 9: identical content → 'skipped' even when override=True
    async def test_skips_when_content_identical(self):
        migrator = self._make_migrator()
        widgets = [{"id": "w1", "width": 2, "height": 2, "config": {}}]
        dash = {"title": "D1", "widgets": copy.deepcopy(widgets)}
        existing = {
            "D1": {"id": "existing-id", "title": "D1", "widgets": copy.deepcopy(widgets)}
        }
        result = await migrator._create_or_update_dashboard_async(
            MagicMock(), dash, override_existing=True, existing_dashboards=existing
        )
        self.assertEqual(result, "skipped")

    # Bug 9: different content → update is triggered
    async def test_updates_when_content_differs(self):
        migrator = self._make_migrator()
        source_widgets = [{"id": "w1", "width": 2, "height": 2, "config": {"new": True}}]
        target_widgets = [{"id": "w1", "width": 2, "height": 2, "config": {}}]
        dash = {"title": "D1", "id": "src-id", "widgets": source_widgets}
        existing = {
            "D1": {"id": "existing-id", "title": "D1", "widgets": target_widgets}
        }
        migrator._update_existing_dashboard_async = AsyncMock(return_value="updated")
        result = await migrator._create_or_update_dashboard_async(
            MagicMock(), dash, override_existing=True, existing_dashboards=existing
        )
        self.assertEqual(result, "updated")
        migrator._update_existing_dashboard_async.assert_awaited_once()

    # POST returns an ID → 'created' (no verify GET needed)
    async def test_post_with_id_returns_created(self):
        migrator = self._make_migrator()
        dash = _make_dashboard()
        existing = {}

        create_resp = self._mock_response(status=200, json_data={"id": "new-id"})
        client = MagicMock()
        client.retry_client.post.return_value = create_resp

        result = await migrator._create_or_update_dashboard_async(
            client, dash, override_existing=False, existing_dashboards=existing
        )
        self.assertEqual(result, "created")
        # No GET should have been made
        client.retry_client.get.assert_not_called()

    # POST returns no ID → 'failed'
    async def test_post_without_id_returns_failed(self):
        migrator = self._make_migrator()
        dash = _make_dashboard()
        existing = {}

        create_resp = self._mock_response(status=200, json_data={})
        client = MagicMock()
        client.retry_client.post.return_value = create_resp

        result = await migrator._create_or_update_dashboard_async(
            client, dash, override_existing=False, existing_dashboards=existing
        )
        self.assertEqual(result, "failed")


class TestMigrateDashboardsAsync(unittest.IsolatedAsyncioTestCase):
    """Bug 10: failed counter is tracked in the return dict."""

    async def test_failed_counted_in_results(self):
        migrator = CustomDashboardsMigratorAsync(_make_config())
        migrator._create_or_update_dashboard_async = AsyncMock(
            side_effect=["created", "failed", "skipped", "failed"]
        )
        results = await migrator._migrate_dashboards_async(
            MagicMock(),
            [MagicMock(), MagicMock(), MagicMock(), MagicMock()],
            override_existing=False,
            existing_dashboards={},
        )
        self.assertEqual(results.count("failed"), 2)
        self.assertEqual(results.count("created"), 1)
        self.assertEqual(results.count("skipped"), 1)

    async def test_unhandled_exception_becomes_failed(self):
        migrator = CustomDashboardsMigratorAsync(_make_config())
        migrator._create_or_update_dashboard_async = AsyncMock(side_effect=RuntimeError("boom"))
        results = await migrator._migrate_dashboards_async(
            MagicMock(), [MagicMock()], override_existing=False, existing_dashboards={}
        )
        self.assertEqual(results, ["failed"])


class TestFindDashboardIdByTitleAsync(unittest.IsolatedAsyncioTestCase):
    """Bug 4: bare except replaced with logged except."""

    async def test_returns_none_and_logs_on_exception(self):
        migrator = CustomDashboardsMigratorAsync(_make_config())
        resp = AsyncMock()
        resp.raise_for_status = MagicMock(side_effect=Exception("network error"))
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        client = MagicMock()
        client.retry_client.get.return_value = resp

        with patch("builtins.print") as mock_print:
            result = await migrator._find_dashboard_id_by_title_async(client, "My Dashboard")

        self.assertIsNone(result)
        # Ensure something was printed (not silently swallowed)
        mock_print.assert_called()
        printed = " ".join(str(c) for c in mock_print.call_args_list)
        self.assertIn("My Dashboard", printed)

    async def test_returns_id_when_found(self):
        migrator = CustomDashboardsMigratorAsync(_make_config())
        resp = AsyncMock()
        resp.raise_for_status = MagicMock()
        resp.json = AsyncMock(return_value=[{"id": "abc", "title": "My Dashboard"}])
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        client = MagicMock()
        client.retry_client.get.return_value = resp

        result = await migrator._find_dashboard_id_by_title_async(client, "My Dashboard")
        self.assertEqual(result, "abc")


if __name__ == "__main__":
    unittest.main()
