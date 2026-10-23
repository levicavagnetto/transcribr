"""`transcribr ravon-check`: prove the instance can log in to Ravon and see the store's calls.

It lists the queues and counts one day's calls per queue. It downloads no audio and prints no
caller numbers.
"""

from datetime import date, datetime, time, timedelta
from typing import TextIO

import httpx

from transcribr.config import Config
from transcribr.ravon.client import Clock, RavonClient, RavonError


def ravon_check(  # noqa: PLR0913 - test seams for transport and clock
    config: Config,
    *,
    day: date,
    queues: list[str] | None,
    out: TextIO,
    transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
) -> int:
    if not config.has_ravon_credentials or config.ravon_password is None:
        print("RAVON_USERNAME and RAVON_PASSWORD are not set. Add them to the .env file.", file=out)
        return 1
    client = RavonClient(
        config.ravon_base_url,
        config.ravon_username,
        config.ravon_password.get_secret_value(),
        transport=transport,
        clock=clock,
    )
    try:
        available = client.queues()
        print(
            f"Logged in to {config.ravon_base_url}. Ravon lists {len(available)} queues.", file=out
        )
        labels = {q.value: q.label for q in available}
        chosen = queues or list(labels)
        start = datetime.combine(day, time(0, 0))
        end = start + timedelta(days=1) - timedelta(seconds=1)
        total = 0
        for queue in chosen:
            count = len(client.search(queue, start, end))
            total += count
            print(
                f"  {queue}  {labels.get(queue, '(not in the queue list)')}  {count} calls",
                file=out,
            )
        print(f"Total: {total} calls on {day.isoformat()} (store local time).", file=out)
        return 0
    except RavonError as error:
        print(f"Ravon check failed: {error}", file=out)
        return 1
    finally:
        client.close()
