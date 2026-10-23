import sqlite3
from pathlib import Path

from tests.ingest.helpers import make_rig


def listed(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM calls ORDER BY id")]


def test_first_start_lists_the_last_seven_days_without_queuing(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.call_ending(60 * 24 * 3, rid=11111111)  # 3 days ago
    rig.call_ending(60 * 24 * 6 + 60, rid=22222222)  # 6 days ago
    rig.call_ending(60 * 24 * 9, rid=33333333)  # 9 days ago: too old for the first listing

    rig.uptime.heartbeat(rig.clock.utcnow())
    result = rig.poller.catch_up()

    assert result.ok
    assert listed(rig.conn) == [11111111, 22222222]
    assert rig.jobs() == []


def test_restart_after_a_weekend_lists_the_missed_calls_without_queuing(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(10, poll_every=2)
    rig.off_for(60 * 48)
    rig.call_ending(60 * 30, rid=44444444)  # during the weekend
    rig.call_ending(60 * 2, rid=55555555)

    rig.uptime.heartbeat(rig.clock.utcnow())
    rig.poller.catch_up()

    assert rig.state_of(44444444) == "not_transcribed"
    assert rig.state_of(55555555) == "not_transcribed"
    assert rig.jobs() == []


def test_a_call_that_ended_just_before_shutdown_is_still_queued(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.run_for(30, poll_every=2)
    rig.call_ending(0.5, rid=66666666)  # ended while running, never polled
    rig.off_for(60)

    rig.uptime.heartbeat(rig.clock.utcnow())
    rig.poller.catch_up()

    assert rig.state_of(66666666) == "waiting"


def test_load_earlier_lists_the_week_before_the_oldest_call(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    rig.call_ending(60 * 24 * 2, rid=11111111)
    rig.call_ending(60 * 24 * 10, rid=22222222)
    rig.call_ending(60 * 24 * 16, rid=33333333)
    rig.uptime.heartbeat(rig.clock.utcnow())
    rig.poller.catch_up()
    assert listed(rig.conn) == [11111111]

    rig.poller.load_earlier()
    assert listed(rig.conn) == [11111111, 22222222]
    rig.poller.load_earlier()
    assert listed(rig.conn) == [11111111, 22222222, 33333333]
    assert rig.jobs() == []
