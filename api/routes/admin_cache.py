"""Admin endpoints for the SQLite cache table.

GET  /admin/cache/audit                    — counts + expiry buckets
POST /admin/cache/clear?namespace=X        — wipe one namespace
POST /admin/cache/clear?expired_only=true  — wipe expired rows only
POST /admin/cache/clear?key=exact          — wipe one key
POST /admin/cache/clear?all=true&confirm=true — nuclear: wipe everything
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.services import cache_admin


router = APIRouter(prefix="/admin/cache", tags=["admin"])


@router.get("/audit")
def cache_audit() -> dict:
    return cache_admin.audit()


@router.post("/clear")
def cache_clear(
    namespace: str | None = Query(None, description="Wipe rows where key starts with namespace:"),
    expired_only: bool = Query(False, description="Wipe only rows whose expires_at < now"),
    key: str | None = Query(None, description="Wipe one exact cache key"),
    all: bool = Query(False, description="DANGER: wipe every cache row"),
    confirm: bool = Query(False, description="Required when all=true"),
) -> dict:
    """Single endpoint for every clear operation — pick exactly one mode.

    Modes (mutually exclusive):
      - expired_only=true       → safe; reclaims disk from stale rows
      - namespace=X             → wipe one namespace (X:%)
      - key=exact_key           → wipe one row
      - all=true + confirm=true → wipe entire cache
    """
    modes_picked = sum([
        bool(namespace), bool(expired_only), bool(key), bool(all),
    ])
    if modes_picked != 1:
        raise HTTPException(
            status_code=400,
            detail="Pick exactly one of: namespace, expired_only, key, all",
        )

    if all:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="all=true requires confirm=true (nuclear option)",
            )
        return cache_admin.clear_all()

    if expired_only:
        return cache_admin.clear_expired()

    if namespace:
        return cache_admin.clear_namespace(namespace)

    if key:
        return cache_admin.clear_key(key)

    # Unreachable — guarded above
    raise HTTPException(status_code=400, detail="No mode specified")
