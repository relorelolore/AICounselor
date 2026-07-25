# app/main.py
from __future__ import annotations
import os
from fastapi import FastAPI

from storage.paths import WEB_DIR
from .routes_health import router as health_router
from .routes_ingest import router as ingest_router
from .routes_chat import router as chat_router   # noqa: E402
from .static_no_store import NoStoreStaticFiles


def create_app() -> FastAPI:
    app = FastAPI(title="AI Counselor", version="0.1.0")
    app.include_router(health_router)
    app.include_router(ingest_router)
    app.include_router(chat_router)
    if os.path.isdir(WEB_DIR):
        # `no-store` so browsers always refetch index.html / app.js / style.css;
        # avoids the stale-JS class of bugs (e.g. citations panel accumulating).
        app.mount(
            "/",
            NoStoreStaticFiles(directory=WEB_DIR, html=True),
            name="web",
        )
    return app


app = create_app()