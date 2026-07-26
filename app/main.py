# app/main.py
from __future__ import annotations
import os

from fastapi import FastAPI, HTTPException

from storage.paths import WEB_DIR
from .admin.routes import router as admin_router
from .routes_chat import router as chat_router
from .routes_health import router as health_router
from .static_no_store import SpaStaticFiles
from storage.admin_db import init as admin_db_init


def create_app() -> FastAPI:
    admin_db_init()  # ensure data/admin.db + default seed exist
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
