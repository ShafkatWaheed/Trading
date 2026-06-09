"""Daily digest endpoints.

GET  /digest                — today's digest (auto-builds if missing)
POST /digest/send           — build + write + email the digest now
GET  /digest/{date}         — read a past digest by YYYY-MM-DD
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.services import daily_digest_service


router = APIRouter(prefix="/digest", tags=["digest"])


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("")
def get_today() -> dict:
    """Returns today's digest, building it on the fly if not yet generated."""
    digest = daily_digest_service.build_digest()
    return digest


@router.post("/send")
def send_now() -> dict:
    """Build + write + email the digest immediately. Use for testing."""
    return daily_digest_service.send_daily_digest()


@router.get("/{date}")
def get_past(date: str) -> dict:
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    p = Path(daily_digest_service._DIGEST_DIR) / f"{date}.md"
    if not p.exists():
        raise HTTPException(status_code=404, detail="no digest for that date")
    return {"date": date, "content": p.read_text(encoding="utf-8"), "path": str(p)}
