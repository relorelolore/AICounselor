# app/static_no_store.py
from __future__ import annotations

import os

from fastapi import Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException


class SpaStaticFiles(StaticFiles):
    """StaticFiles for the built Vue SPA (``web/dist``).

    - ``Cache-Control: no-store`` on everything: local-dev app, no CDN, so
      disabling cache costs nothing and eliminates the "old JS still running"
      class of bugs. (Hashed assets could be cached, but no-store keeps the
      mental model simple.)
    - SPA history fallback: unknown GET/HEAD paths (e.g. ``/admin``,
      ``/admin/settings``) serve ``index.html`` so Vue Router can take over.
    """

    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            resp: Response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and scope.get("method") in ("GET", "HEAD"):
                resp = FileResponse(os.path.join(self.directory, "index.html"))
            else:
                raise
        resp.headers["Cache-Control"] = "no-store"
        return resp
