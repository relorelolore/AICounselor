# app/static_no_store.py
from __future__ import annotations

from fastapi import Response
from fastapi.staticfiles import StaticFiles


class NoStoreStaticFiles(StaticFiles):
    """StaticFiles with ``Cache-Control: no-store`` so browsers always pick up
    the latest ``app.js`` / ``index.html`` / ``style.css``. Local-dev SPA —
    no CDN, so disabling cache costs nothing and eliminates the
    "old JS still running" class of bugs (e.g. stale citations panel)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope: dict) -> Response:
        resp: Response = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store"
        return resp