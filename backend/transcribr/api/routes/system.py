"""Health and status: open to everyone on the shop network."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from transcribr.admin import Admins
from transcribr.api.deps import AdminsDep, Db, Now, get_config
from transcribr.config import Config
from transcribr.settings import RESEARCH_PROMPT, Settings
from transcribr.status import build_status
from transcribr.store.state import CHECK_REQUESTED, LAST_POLL_OK, State

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
def health(conn: Db) -> dict[str, str]:
    conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/status")
def status(
    conn: Db, now: Now, admins: AdminsDep, config: Annotated[Config, Depends(get_config)]
) -> dict[str, Any]:
    report = build_status(
        conn,
        now=now,
        credentials_present=config.has_ravon_credentials,
        admin_exists=Admins.exists(admins),
    )
    return report.as_dict()


@router.get("/research-prompt")
def research_prompt(conn: Db) -> dict[str, str]:
    """The prompt Copy for ChatGPT puts first. Anyone can read it; only the admin changes it."""
    return {"prompt": Settings(conn).get(RESEARCH_PROMPT)}


@router.post("/check-ravon")
def check_ravon(conn: Db) -> dict[str, object]:
    """Ask the worker to check Ravon for new calls now, instead of at its next scheduled poll.

    The worker picks this up within about a second, or right after the call it is
    transcribing; a press within 15 seconds of the last check causes no extra request.
    `last_poll_ok` lets the caller tell when the check has happened.
    """
    state = State(conn)
    state.set(CHECK_REQUESTED, True)
    return {"requested": True, "last_poll_ok": state.get(LAST_POLL_OK)}
