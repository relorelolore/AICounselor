# app/main.py
from __future__ import annotations
import os

from fastapi import FastAPI, HTTPException

from llm.config import (
    update_embedding_settings,
    update_llm_settings,
    update_rag_settings,
)
from storage.paths import WEB_DIR
from .admin.routes import router as admin_router
from .admin.settings import get_effective_settings
from .routes_chat import router as chat_router
from .routes_health import router as health_router
from .static_no_store import SpaStaticFiles
from storage.admin_db import init as admin_db_init


def _load_admin_settings_into_singletons() -> None:
    """Apply admin DB-stored overrides to runtime singletons at startup.

    Without this, `_llm_cfg` and friends start from env-var defaults and
    forget any admin-configured values across process restarts (including
    uvicorn --reload). Applying the effective settings here makes admin
    changes survive restarts.

    REQUIRES_RESTART remains informational in the admin UI; we apply all
    hot-reloadable fields plus the (currently also hot-reloadable in chat)
    base_url / model_name / timeout so that --reload and full restarts
    produce a consistent process. `paths` is intentionally not applied —
    it's truly restart-required (chroma collection name cannot change
    in-place without rebuilding the collection).
    """
    eff = get_effective_settings()
    update_llm_settings(eff["llm"])
    update_rag_settings(eff["retrieval"])
    update_embedding_settings(eff["embedding"])


def create_app() -> FastAPI:
    admin_db_init()  # ensure data/admin.db + default seed exist
    _load_admin_settings_into_singletons()  # pick up admin DB overrides
    app = FastAPI(title="AI Counselor", version="0.1.0")
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(admin_router, prefix="/api/admin")

    # Keep unknown API paths out of the root static-file mount, which otherwise
    # reports POST requests as 405 instead of the API-standard 404.
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def api_not_found(path: str) -> None:
        raise HTTPException(status_code=404, detail="Not Found")

    if os.path.isdir(WEB_DIR):
        # Vue SPA 构建产物（web/dist）。no-store + history fallback：
        # /admin、/admin/settings 等前端路由直达时返回 index.html。
        app.mount(
            "/",
            SpaStaticFiles(directory=WEB_DIR, html=True),
            name="web",
        )
    return app


app = create_app()
