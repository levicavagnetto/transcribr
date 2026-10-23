"""Health and status: open to everyone on the shop network."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from transcribr.admin import Admins
from transcribr.api.deps import AdminsDep, Db, Now, get_config
from transcribr.config import Config
from transcribr.status import build_status

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
