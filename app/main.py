# app/main.py
from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from storage.paths import WEB_DIR
from .routes_health import router as health_router
from .routes_ingest import router as ingest_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Counselor", version="0.1.0")
    app.include_router(health_router)
    app.include_router(ingest_router)
    if os.path.isdir(WEB_DIR):
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()