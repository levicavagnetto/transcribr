"""Reading the queue list and the search results out of Ravon's recordings page.

The results are not in the HTML table: the page calls `$("#recordingTable").DataTable({ data:
[...] })` with a JSON array, one object per call. Anything unexpected raises PageFormatChanged
so a changed page is noticed instead of silently returning no calls.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

_DATATABLE = re.compile(
    r"""\$\(\s*["']#recordingTable["']\s*\)\s*\.DataTable\(\s*\{\s*data\s*:\s*"""
)
_CHECKBOX_VALUE = re.compile(r"""value\s*=\s*['"]([1-9]\d{4,11})['"]""")
_START_FORMAT = "%Y-%m-%d %H:%M:%S"


class PageFormatChanged(Exception):
    """Ravon's page no longer looks the way the parser expects."""


@dataclass(frozen=True)
class Queue:
    value: str
    label: str


@dataclass(frozen=True)
class Recording:
    id: int
    start_local: str
    minutes: float
    caller: str
    answered_by: str


class _QueueSelect(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found = False
        self._inside = False
        self._value: str | None = None
        self._label: list[str] = []
        self.options: list[Queue] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "select" and attributes.get("name") == "queue":
            self.found = True
            self._inside = True
        elif tag == "option" and self._inside:
            self._value = attributes.get("value") or ""
            self._label = []

    def handle_data(self, data: str) -> None:
        if self._value is not None:
            self._label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._value is not None:
            if self._value:
                self.options.append(Queue(self._value, "".join(self._label).strip()))
            self._value = None
        elif tag == "select":
            self._inside = False


def parse_queues(html: str) -> list[Queue]:
    parser = _QueueSelect()
    parser.feed(html)
    parser.close()
    if not parser.found:
        raise PageFormatChanged("the queue dropdown is missing from the recordings page")
    return parser.options


def _row(raw: Any) -> Recording:
    if not isinstance(raw, dict):
        raise PageFormatChanged("a DataTable row is not an object")
    row: dict[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
    try:
        select, start, minutes = str(row["select"]), str(row["Start Time"]), row["Minutes"]
        caller, answered_by = str(row["From"]), str(row["To"])
    except KeyError as missing:
        raise PageFormatChanged(f"a DataTable row has no {missing} field") from None
    match = _CHECKBOX_VALUE.search(select)
    if match is None:
        raise PageFormatChanged("a DataTable row has no recording ID in its checkbox")
    try:
        datetime.strptime(start, _START_FORMAT)
    except ValueError:
        raise PageFormatChanged(f"unexpected Start Time format: {start!r}") from None
    try:
        length = float(minutes)
    except TypeError, ValueError:
        raise PageFormatChanged(f"unexpected Minutes value: {minutes!r}") from None
    return Recording(int(match.group(1)), start, length, caller.strip(), answered_by.strip())


def parse_recordings(html: str) -> list[Recording]:
    match = _DATATABLE.search(html)
    if match is None:
        raise PageFormatChanged("the DataTable script with the call rows is missing")
    try:
        data, _ = json.JSONDecoder().raw_decode(html, match.end())
    except json.JSONDecodeError as error:
        raise PageFormatChanged(f"the DataTable rows are not valid JSON: {error}") from None
    if not isinstance(data, list):
        raise PageFormatChanged("the DataTable data is not a list")
    rows: list[Any] = data  # pyright: ignore[reportUnknownVariableType]
    return [_row(raw) for raw in rows]
