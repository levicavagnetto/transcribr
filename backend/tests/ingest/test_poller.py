from pathlib import Path

from tests.ingest.helpers import AFTER_HOURS, STILLWATER, make_rig
from transcribr.settings import STORE_QUEUES, Settings
from transcribr.store.state import LAST_POLL_OK, RAVON_STATE, State


def test_a_new_call_is_listed_with_its_details(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(10)
    call = rig.call_ending(2, rid=26541125)
    rig.poller.poll()
    row = rig.conn.execute("SELECT * FROM calls WHERE id = 26541125").fetchone()
    assert row["queue"] == STILLWATER
    assert row["start_local"] == call.start_local
    assert row["minutes"] == 3.0
    assert row["caller_number"] == "(405) 555-0100"
    assert row["answered_by"] == "SW Counter Sales"
    assert row["start_utc"].endswith("Z")


def test_the_same_call_from_overlapping_polls_is_one_record(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(10, poll_every=2)
    rig.call_ending(5, rid=26541125)
    rig.poller.poll()
    rig.run_for(2)
    rig.poller.poll()
    assert rig.conn.execute("SELECT count(*) FROM calls").fetchone()[0] == 1
    assert rig.jobs() == [26541125]


def test_an_empty_result_is_a_successful_poll(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    result = rig.poller.poll()
    assert result.ok
    assert State(rig.conn).get(LAST_POLL_OK) is not None
    assert State(rig.conn).get(RAVON_STATE) == "ok"


def test_later_polls_search_from_two_hours_before_the_last_success(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.poller.poll()  # at 09:00 store time
    rig.run_for(10)
    rig.poller.poll()
    windows = rig.search_windows()
    assert windows[-1][0] == STILLWATER
    assert windows[-1][1] == "2026-10-22 07:00:00"


def test_a_call_that_ends_while_the_server_runs_is_queued(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(30, poll_every=2)
    rig.call_ending(1, rid=26541125)
    rig.run_for(3, poll_every=2)
    assert rig.state_of(26541125) == "waiting"
    assert rig.jobs() == [26541125]


def test_a_call_that_ends_while_the_server_is_off_is_listed_only(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(10, poll_every=2)
    rig.off_for(60)
    rig.call_ending(30, rid=26541125)  # ended in the middle of the downtime
    rig.run_for(3, poll_every=2)
    assert rig.state_of(26541125) == "not_transcribed"
    assert rig.jobs() == []


def test_calls_during_a_ravon_outage_are_still_queued(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(10, poll_every=2)
    rig.fake.server_errors = 10_000
    rig.call_ending(-5, rid=26541125)  # ends 5 minutes into the outage
    rig.run_for(20, poll_every=2)
    assert State(rig.conn).get(RAVON_STATE) == "unreachable"
    rig.fake.server_errors = 0
    rig.run_for(15, poll_every=2)
    assert State(rig.conn).get(RAVON_STATE) == "ok"
    assert rig.state_of(26541125) == "waiting"


def test_a_queue_added_later_lists_its_earlier_calls_without_queuing(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(30, poll_every=2)
    rig.call_ending(10, rid=26541130, queue=AFTER_HOURS)  # while running, before it was followed
    Settings(rig.conn).set(STORE_QUEUES, [STILLWATER, AFTER_HOURS])
    rig.run_for(3, poll_every=2)
    assert rig.state_of(26541130) == "not_transcribed"
    rig.call_ending(-1, rid=26541131, queue=AFTER_HOURS)  # after it was followed
    rig.run_for(4, poll_every=2)
    assert rig.state_of(26541131) == "waiting"


def test_no_queues_chosen_means_no_contact(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, queues=[])
    result = rig.poller.poll()
    assert not result.ok
    assert result.state == "no_queues"
    assert rig.fake.requests == []


def test_missing_credentials_are_recorded_without_contact(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, credentials=False)
    rig.poller.poll()
    assert State(rig.conn).get(RAVON_STATE) == "no_credentials"
    assert rig.fake.requests == []


def test_a_rejected_login_is_recorded(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.fake.reject_logins = True
    rig.poller.poll()
    assert State(rig.conn).get(RAVON_STATE) == "login_failed"


def test_a_changed_page_is_recorded(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.fake.page_format_changed = True
    rig.poller.poll()
    assert State(rig.conn).get(RAVON_STATE) == "page_format_changed"
