import pytest

from tests.fake_ravon.app import FakeCall, FakeRavon
from transcribr.ravon.parse import (
    PageFormatChanged,
    Queue,
    Recording,
    parse_queues,
    parse_recordings,
)


def page(fake: FakeRavon, rows: list[FakeCall]) -> str:
    return fake._search_page(rows).text  # pyright: ignore[reportPrivateUsage]


def test_queue_list_skips_the_all_option() -> None:
    queues = parse_queues(page(FakeRavon(), []))
    assert queues == [
        Queue("tireProz-salescustserv", "Stillwater Sales/CS (x600)"),
        Queue("tireProz-SWafterHRS", "SWafterHRS (x599)"),
        Queue("tireProz-HDsales", "Hudson Sales/CS (x700)"),
    ]


def test_queue_labels_are_unescaped() -> None:
    fake = FakeRavon(queues={"q&a": "Parts & Service <x1>"})
    assert parse_queues(page(fake, [])) == [Queue("q&a", "Parts & Service <x1>")]


def test_missing_queue_select_is_a_format_change() -> None:
    with pytest.raises(PageFormatChanged, match="queue"):
        parse_queues("<html><body><select name='user'></select></body></html>")


def test_rows_are_read_from_the_datatable_script() -> None:
    fake = FakeRavon()
    rows = [
        FakeCall(26541125, "q", "2026-10-22 10:42:00", 6.2, "(405) 555-0142", "SW Counter Sales"),
        FakeCall(26541126, "q", "2026-10-22 10:50:13", 0.0, "Anonymous", "Judd D Andrews"),
    ]
    assert parse_recordings(page(fake, rows)) == [
        Recording(26541125, "2026-10-22 10:42:00", 6.2, "(405) 555-0142", "SW Counter Sales"),
        Recording(26541126, "2026-10-22 10:50:13", 0.0, "Anonymous", "Judd D Andrews"),
    ]


def test_empty_result_is_an_empty_list() -> None:
    assert parse_recordings(page(FakeRavon(), [])) == []


def test_missing_table_script_is_a_format_change() -> None:
    fake = FakeRavon(page_format_changed=True)
    with pytest.raises(PageFormatChanged, match="DataTable"):
        parse_recordings(page(fake, []))


@pytest.mark.parametrize(
    "row",
    [
        {"Start Time": "2026-10-22 10:42:00", "Minutes": "1", "From": "x", "To": "y"},  # no select
        {
            "select": "<input type='checkbox' name='checked' />",  # no value
            "Start Time": "2026-10-22 10:42:00",
            "Minutes": "1",
            "From": "x",
            "To": "y",
        },
        {
            "select": "<input value='26541125' />",
            "Start Time": "22/10/2026",  # wrong date format
            "Minutes": "1",
            "From": "x",
            "To": "y",
        },
        {
            "select": "<input value='26541125' />",
            "Start Time": "2026-10-22 10:42:00",
            "Minutes": "lots",
            "From": "x",
            "To": "y",
        },
    ],
)
def test_malformed_rows_are_a_format_change(row: dict[str, str]) -> None:
    import json

    html = f'<script>$("#recordingTable").DataTable({{ data: {json.dumps([row])} }});</script>'
    with pytest.raises(PageFormatChanged):
        parse_recordings(html)


def test_minutes_may_be_a_number_or_a_string() -> None:
    html = (
        '<script>$("#recordingTable").DataTable({ data: [{"select": "<input value=\'12345678\'/>",'
        ' "Start Time": "2026-10-22 10:42:00", "Minutes": 2.5, "From": "a", "To": "b"}]'
        " });</script>"
    )
    assert parse_recordings(html)[0].minutes == 2.5
