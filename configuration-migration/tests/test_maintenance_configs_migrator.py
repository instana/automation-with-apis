"""Unit tests for the MaintenanceConfigsMigrator class."""

import pytest
import json
import requests
from unittest.mock import patch, mock_open, MagicMock
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'maintenance-configs'))
from migrator import MaintenanceConfigsMigrator, SERVER_COMPUTED_FIELDS
from config import Config


def _response(status_code=200, payload=None, text=""):
    """Build a mock requests response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = text
    return response


def _http_error(status_code=400, payload=None):
    """Build a RequestException carrying a response, as raise_for_status does."""
    error = requests.exceptions.HTTPError("API Error")
    error.response = _response(status_code=status_code, payload=payload)
    return error


# Year 2100, so the default fixture is a window the backend would accept. A
# past start makes a one-time window unmigratable, which most tests do not want.
FUTURE_START = 4102444800000


def _one_time(start=FUTURE_START, amount=2, unit="HOURS"):
    """Build a ONE_TIME scheduling block."""
    return {"type": "ONE_TIME", "start": start, "duration": {"amount": amount, "unit": unit}}


def _recurrent(start=1700000000000, rrule="FREQ=WEEKLY;BYDAY=SU", tz="Europe/Berlin"):
    """Build a RECURRENT scheduling block."""
    return {
        "type": "RECURRENT",
        "start": start,
        "duration": {"amount": 30, "unit": "MINUTES"},
        "rrule": rrule,
        "timezoneId": tz,
    }


def _config(cid="mc1", name="Nightly patching", query="entity.zone:prod", scheduling=None):
    """Build a maintenance configuration as the API would return it."""
    return {
        "id": cid,
        "name": name,
        "query": query,
        "scheduling": scheduling or _one_time(),
        "paused": False,
        "retriggerOpenAlertsEnabled": True,
        "tagFilterExpressionEnabled": False,
    }


class TestMaintenanceConfigsMigrator:
    """Test cases for the MaintenanceConfigsMigrator class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config()
        self.config.source_token = "source_token"
        self.config.source_url = "https://source.com"
        self.config.target_token = "target_token"
        self.config.target_url = "https://target.com"
        self.config.verify_ssl = True
        self.config.events_source = "file"
        self.config.events_file_path = "test_maintenance.json"
        # Default is "ask", which would try to read stdin during tests.
        self.config.on_duplicate = "skip"

        self.migrator = MaintenanceConfigsMigrator(self.config)

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def test_init_uses_v2_endpoint(self):
        """The v1 maintenance API is deprecated, so v2 must be used."""
        assert self.migrator.req_maintenance == "/api/settings/v2/maintenance"

    @patch('migrator.urllib3.disable_warnings')
    def test_init_with_ssl_disabled(self, mock_disable_warnings):
        """Test migrator initialization with SSL verification disabled."""
        self.config.verify_ssl = False
        MaintenanceConfigsMigrator(self.config)

        mock_disable_warnings.assert_called_once()

    # ------------------------------------------------------------------
    # Transformation
    # ------------------------------------------------------------------

    def test_prepare_strips_server_computed_fields(self):
        """Fields the write endpoint does not accept must be removed."""
        source = _config()
        source.update({
            "applicationNames": ["app-a"],
            "occurrence": {"start": 1, "end": 2},
            "invalid": False,
            "lastUpdated": 1700000001234,
            "state": "SCHEDULED",
            # Real backends return this even though it is absent from the
            # documented write schema.
            "validVersion": 1,
        })

        payload = self.migrator._prepare_config(source)

        for field in SERVER_COMPUTED_FIELDS:
            assert field not in payload, f"{field} should have been stripped"

    def test_prepare_keeps_writable_fields(self):
        """Everything the write endpoint accepts must survive."""
        source = _config()
        source["tagFilterExpression"] = {
            "type": "EXPRESSION",
            "logicalOperator": "AND",
            "elements": [
                {"type": "TAG_FILTER", "name": "agent.tag", "operator": "EQUALS", "value": "prod"}
            ],
        }
        source["tagFilterExpressionEnabled"] = True

        payload = self.migrator._prepare_config(source)

        for field in ('id', 'name', 'query', 'scheduling', 'paused',
                      'retriggerOpenAlertsEnabled', 'tagFilterExpression',
                      'tagFilterExpressionEnabled'):
            assert field in payload, f"{field} should have been kept"

    def test_prepare_preserves_the_source_id(self):
        """The ID must be preserved: the write endpoint is keyed on it."""
        payload = self.migrator._prepare_config(_config(cid="keep-me"))

        assert payload['id'] == "keep-me"

    def test_prepare_preserves_recurrence_details(self):
        """rrule and timezoneId are what make a recurrent window recurrent."""
        source = _config(scheduling=_recurrent(rrule="FREQ=DAILY", tz="America/New_York"))

        payload = self.migrator._prepare_config(source)

        assert payload['scheduling']['rrule'] == "FREQ=DAILY"
        assert payload['scheduling']['timezoneId'] == "America/New_York"

    @pytest.mark.parametrize("missing", ['id', 'name', 'query', 'scheduling'])
    def test_prepare_rejects_missing_required_field(self, missing):
        """Each of the four required fields is checked before any request."""
        source = _config()
        del source[missing]

        assert self.migrator._prepare_config(source) is None

    def test_prepare_rejects_non_dict_scheduling(self):
        """Scheduling must be an object."""
        source = _config()
        source['scheduling'] = "ONE_TIME"

        assert self.migrator._prepare_config(source) is None

    @pytest.mark.parametrize("missing", ['type', 'start', 'duration'])
    def test_prepare_rejects_incomplete_scheduling(self, missing):
        """Scheduling needs type, start and duration regardless of type."""
        source = _config()
        del source['scheduling'][missing]

        assert self.migrator._prepare_config(source) is None

    def test_prepare_rejects_recurrent_without_rrule(self):
        """A recurrent window with no rrule has no schedule to recur on."""
        source = _config(scheduling=_recurrent())
        del source['scheduling']['rrule']

        assert self.migrator._prepare_config(source) is None

    def test_prepare_allows_start_of_zero(self):
        """start=0 is falsy but a legitimate epoch value, so must be allowed."""
        source = _config(scheduling=_one_time(start=0))

        assert self.migrator._prepare_config(source) is not None

    def test_prepare_allows_empty_query(self):
        """An empty query is legitimate and common: the window is unscoped.

        Testing query for truthiness rather than presence would wrongly skip
        these, and real backends have plenty of them.
        """
        source = _config(query="")

        payload = self.migrator._prepare_config(source)

        assert payload is not None
        assert payload['query'] == ""

    def test_prepare_rejects_query_that_is_absent(self):
        """A missing query is still an error, unlike an empty one."""
        source = _config()
        del source['query']

        assert self.migrator._prepare_config(source) is None

    @pytest.mark.parametrize("field", ['id', 'name'])
    def test_prepare_rejects_empty_identifier(self, field):
        """id and name identify the configuration, so empty is not acceptable."""
        source = _config()
        source[field] = ""

        assert self.migrator._prepare_config(source) is None

    # ------------------------------------------------------------------
    # Expired one-time windows
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("state,expected", [
        ('EXPIRED', 'already expired'),
        ('UNSCHEDULED', 'already unscheduled'),
    ])
    def test_states_the_backend_rejects(self, state, expected):
        """The backend answers 400 for these, so they are skipped up front."""
        source = _config()
        source['state'] = state

        assert self.migrator._unmigratable_reason(source) == expected

    @pytest.mark.parametrize("state", ['ACTIVE', 'SCHEDULED', 'PAUSED'])
    def test_states_the_backend_accepts(self, state):
        """These migrate normally."""
        source = _config()
        source['state'] = state

        assert self.migrator._unmigratable_reason(source) is None

    def test_recurrent_window_can_also_be_expired(self):
        """A recurrent window expires too, e.g. an rrule with UNTIL or COUNT.

        Inferring expiry from the start time alone would miss these, and real
        backends have many of them.
        """
        source = _config(scheduling=_recurrent(start=1000))
        source['state'] = 'EXPIRED'

        assert self.migrator._unmigratable_reason(source) == 'already expired'

    def test_falls_back_to_start_time_without_state(self):
        """A hand-written source file has no state, so infer what we can."""
        past = _config(scheduling=_one_time(start=1000))
        future = _config(scheduling=_one_time(start=4102444800000))  # year 2100

        assert self.migrator._unmigratable_reason(past) == 'already expired'
        assert self.migrator._unmigratable_reason(future) is None

    def test_fallback_cannot_judge_recurrent(self):
        """Without state, a recurrent window's expiry is not inferable."""
        source = _config(scheduling=_recurrent(start=1000))

        assert self.migrator._unmigratable_reason(source) is None

    # ------------------------------------------------------------------
    # Source acquisition
    # ------------------------------------------------------------------

    def test_load_from_bare_list_file(self):
        """A bare JSON array of configurations is accepted."""
        configs = [_config(cid="a"), _config(cid="b")]

        with patch('builtins.open', mock_open(read_data=json.dumps(configs))):
            assert self.migrator._get_source_configs() == configs

    def test_load_from_envelope_file(self):
        """The export envelope is unwrapped."""
        configs = [_config()]
        envelope = {"version": 1, "resource": "maintenance-configs",
                    "maintenanceConfigs": configs}

        with patch('builtins.open', mock_open(read_data=json.dumps(envelope))):
            assert self.migrator._get_source_configs() == configs

    def test_load_from_file_not_found(self):
        """A missing file returns None, not an empty list."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            assert self.migrator._get_source_configs() is None

    def test_load_from_file_invalid_json(self):
        """Invalid JSON returns None."""
        with patch('builtins.open', mock_open(read_data="{not json")):
            assert self.migrator._get_source_configs() is None

    def test_load_from_envelope_without_expected_key(self):
        """An object lacking the maintenanceConfigs array returns None."""
        with patch('builtins.open', mock_open(read_data=json.dumps({"version": 1}))):
            assert self.migrator._get_source_configs() is None

    @patch('migrator.requests.get')
    def test_fetch_from_api_writes_envelope(self, mock_get):
        """Fetched configurations are persisted for reuse."""
        self.config.events_source = "api"
        mock_get.return_value = _response(payload=[_config()])

        handle = mock_open()
        with patch('builtins.open', handle):
            configs = self.migrator._get_source_configs()

        assert len(configs) == 1
        written = "".join(c.args[0] for c in handle().write.call_args_list)
        envelope = json.loads(written)
        assert envelope['resource'] == "maintenance-configs"
        assert envelope['maintenanceConfigs'][0]['id'] == "mc1"

    @patch('migrator.requests.get')
    def test_fetch_survives_unwritable_file(self, mock_get):
        """A read-only working directory must not abort the migration."""
        self.config.events_source = "api"
        mock_get.return_value = _response(payload=[_config()])

        with patch('builtins.open', side_effect=OSError("read-only")):
            assert self.migrator._get_source_configs() is not None

    @patch('migrator.requests.get')
    def test_fetch_from_api_error(self, mock_get):
        """A source API failure returns None."""
        self.config.events_source = "api"
        mock_get.side_effect = requests.exceptions.RequestException("boom")

        assert self.migrator._get_source_configs() is None

    @patch('migrator.requests.get')
    def test_fetch_from_api_non_list(self, mock_get):
        """A JSON error object where a list is expected is a failure."""
        self.config.events_source = "api"
        mock_get.return_value = _response(payload={"error": "nope"})

        assert self.migrator._get_source_configs() is None

    def test_source_file_path_avoids_shared_default(self):
        """The shared events default is redirected to a maintenance file."""
        self.config.events_file_path = "source_events.json"

        assert self.migrator._resolve_source_file_path() == "source_maintenance_configs.json"

    def test_source_file_path_honors_explicit_value(self):
        """An explicit path is used as given."""
        self.config.events_file_path = "my_windows.json"

        assert self.migrator._resolve_source_file_path() == "my_windows.json"

    # ------------------------------------------------------------------
    # Target acquisition
    # ------------------------------------------------------------------

    @patch('migrator.requests.get')
    def test_get_target_configs(self, mock_get):
        """Test getting target configurations."""
        configs = [_config(cid="t1")]
        mock_get.return_value = _response(payload=configs)

        assert self.migrator._get_target_configs() == configs

    @patch('migrator.requests.get')
    def test_get_target_error_returns_none(self, mock_get):
        """A target failure must return None, never an empty list.

        Returning [] would make an unreadable target indistinguishable from an
        empty one, and every source configuration would be written to it.
        """
        mock_get.side_effect = requests.exceptions.RequestException("boom")

        assert self.migrator._get_target_configs() is None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @patch('migrator.requests.put')
    def test_put_uses_the_id_in_the_path(self, mock_put):
        """The write endpoint is keyed on the ID, which preserves it."""
        mock_put.return_value = _response()

        assert self.migrator._put_config(_config(cid="abc123"), "Nightly") is True
        assert mock_put.call_args.args[0] == \
            "https://target.com/api/settings/v2/maintenance/abc123"

    @patch('migrator.requests.put')
    def test_put_sends_the_whole_payload(self, mock_put):
        """The body carries the configuration, including its ID."""
        mock_put.return_value = _response()
        payload = _config(cid="abc123")

        self.migrator._put_config(payload, "Nightly")

        assert mock_put.call_args.kwargs['json'] == payload

    @patch('migrator.requests.put')
    def test_put_failure_reported(self, mock_put):
        """A failed write returns False rather than raising."""
        mock_put.side_effect = _http_error(400, {"errors": ["bad request"]})

        assert self.migrator._put_config(_config(), "Nightly") is False

    # ------------------------------------------------------------------
    # Duplicate handling
    # ------------------------------------------------------------------

    @patch('builtins.input')
    def test_configured_duplicate_action_skips_prompt(self, mock_input):
        """A configured on_duplicate is used without prompting."""
        for value in ('skip', 'update'):
            self.config.on_duplicate = value
            assert self.migrator._prompt_for_duplicate_config("Nightly") == value
        mock_input.assert_not_called()

    @patch('migrator.sys.stdin.isatty', return_value=True)
    @patch('builtins.input', side_effect=['bogus', 'u'])
    def test_prompt_reprompts_on_invalid_input(self, mock_input, mock_isatty):
        """An invalid choice re-prompts."""
        self.config.on_duplicate = "ask"

        assert self.migrator._prompt_for_duplicate_config("Nightly") == "update"
        assert mock_input.call_count == 2

    @patch('migrator.sys.stdin.isatty', return_value=False)
    def test_prompt_without_tty_defaults_to_skip(self, mock_isatty):
        """Without a TTY, ask degrades to skip rather than blocking."""
        self.config.on_duplicate = "ask"

        assert self.migrator._prompt_for_duplicate_config("Nightly") == "skip"

    # ------------------------------------------------------------------
    # migrate()
    # ------------------------------------------------------------------

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_all_new(self, mock_source, mock_target, mock_put):
        """All-new configurations are created."""
        mock_source.return_value = [_config(cid="a"), _config(cid="b")]
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert result == {"source": 2, "migrated": 2, "updated": 0,
                          "skipped": 0, "failed": 0}
        assert mock_put.call_count == 2

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_existing_id_skipped(self, mock_source, mock_target, mock_put):
        """In skip mode an existing ID is left alone and not written."""
        self.config.on_duplicate = "skip"
        mock_source.return_value = [_config(cid="a")]
        mock_target.return_value = [_config(cid="a")]

        result = self.migrator.migrate()

        assert result['skipped'] == 1
        assert result['migrated'] == 0
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_existing_id_updated(self, mock_source, mock_target, mock_put):
        """In update mode an existing ID counts as updated, not migrated."""
        self.config.on_duplicate = "update"
        mock_source.return_value = [_config(cid="a")]
        mock_target.return_value = [_config(cid="a")]

        result = self.migrator.migrate()

        assert result['updated'] == 1
        assert result['migrated'] == 0
        mock_put.assert_called_once()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_identity_is_id_not_name(self, mock_source, mock_target, mock_put):
        """Matching is by ID, so a renamed target config is still the same one.

        This is the advantage of an API that lets the caller choose the ID: no
        name-based matching, so a rename in the target cannot create a
        duplicate.
        """
        self.config.on_duplicate = "skip"
        mock_source.return_value = [_config(cid="a", name="Original name")]
        mock_target.return_value = [_config(cid="a", name="Renamed in target")]

        result = self.migrator.migrate()

        assert result['skipped'] == 1
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_prompt_for_duplicate_config', return_value='cancel')
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_cancel_stops_the_loop(self, mock_source, mock_target, mock_prompt, mock_put):
        """Cancelling leaves the remaining configurations untouched."""
        self.config.on_duplicate = "ask"
        mock_source.return_value = [_config(cid="a"), _config(cid="b")]
        mock_target.return_value = [_config(cid="a")]

        result = self.migrator.migrate()

        assert result['migrated'] == 0
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_does_not_attempt_rejected_states(self, mock_source, mock_target, mock_put):
        """Windows the backend refuses are skipped without a request.

        Sending them produces 400 "already expired", so attempting them wastes a
        request each and reports a correct run as having failures. On a
        long-lived source most windows are in this state.
        """
        expired = _config(cid="a", name="Old one")
        expired['state'] = 'EXPIRED'
        unscheduled = _config(cid="b", name="Never scheduled")
        unscheduled['state'] = 'UNSCHEDULED'
        good = _config(cid="c", name="Upcoming")
        good['state'] = 'SCHEDULED'

        mock_source.return_value = [expired, unscheduled, good]
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert result['migrated'] == 1
        assert result['skipped'] == 2
        assert result['failed'] == 0, "rejected states must not count as failures"
        assert mock_put.call_count == 1, "only the migratable window is sent"

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_rejected_state_checked_before_duplicate_prompt(self, mock_source, mock_target, mock_put):
        """An unmigratable window is skipped without prompting about duplicates."""
        self.config.on_duplicate = "ask"
        expired = _config(cid="a")
        expired['state'] = 'EXPIRED'
        mock_source.return_value = [expired]
        mock_target.return_value = [_config(cid="a")]

        with patch.object(self.migrator, '_prompt_for_duplicate_config') as mock_prompt:
            result = self.migrator.migrate()

        assert result['skipped'] == 1
        mock_prompt.assert_not_called()
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs', return_value=None)
    def test_migrate_no_source(self, mock_source):
        """A source failure returns a zeroed result carrying every key."""
        result = self.migrator.migrate()

        assert result == {"source": 0, "migrated": 0, "updated": 0,
                          "skipped": 0, "failed": 0}

    @patch.object(MaintenanceConfigsMigrator, '_put_config')
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs', return_value=None)
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_no_target_writes_nothing(self, mock_source, mock_target, mock_put):
        """An unreadable target must abort, not write every source config."""
        mock_source.return_value = [_config()]

        result = self.migrator.migrate()

        assert result['source'] == 1
        assert result['migrated'] == 0
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=False)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_write_failure_counted(self, mock_source, mock_target, mock_put):
        """A failed write is reported as failed, not migrated."""
        mock_source.return_value = [_config()]
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert result['failed'] == 1
        assert result['migrated'] == 0

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_skips_unusable_records(self, mock_source, mock_target, mock_put):
        """Records missing an id or name never reach the write step."""
        mock_source.return_value = [{"name": "No ID"}, {"id": "no-name"}]
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert result['skipped'] == 2
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_put_config', return_value=True)
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_skips_records_failing_validation(self, mock_source, mock_target, mock_put):
        """A config that cannot be prepared is skipped, not sent."""
        bad = _config(cid="bad")
        del bad['scheduling']['duration']
        mock_source.return_value = [bad]
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert result['skipped'] == 1
        mock_put.assert_not_called()

    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_result_always_has_canonical_keys(self, mock_source, mock_target):
        """cli.py reads migrated and updated, so both must always be present."""
        mock_source.return_value = []
        mock_target.return_value = []

        result = self.migrator.migrate()

        assert {"source", "migrated", "updated", "skipped"} <= set(result.keys())

    @patch('migrator.requests.put')
    @patch.object(MaintenanceConfigsMigrator, '_get_target_configs')
    @patch.object(MaintenanceConfigsMigrator, '_get_source_configs')
    def test_migrate_strips_computed_fields_before_writing(self, mock_source, mock_target, mock_put):
        """End to end: the request body must not carry server-computed fields."""
        source = _config()
        source.update({"state": "ACTIVE", "invalid": False, "lastUpdated": 1,
                       "occurrence": {"start": 1, "end": 2}, "applicationNames": []})
        mock_source.return_value = [source]
        mock_target.return_value = []
        mock_put.return_value = _response()

        self.migrator.migrate()

        sent = mock_put.call_args.kwargs['json']
        for field in SERVER_COMPUTED_FIELDS:
            assert field not in sent
