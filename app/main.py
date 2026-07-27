# app/main.py
from __future__ import annotations
import os

# Patch chromadb 0.6.x's posthog telemetry call to match posthog >= 7.x's
# signature. chromadb's Posthog._direct_capture calls
# `posthog.capture(distinct_id, event_name, properties)` with 3 positional
# args; posthog 7.x changed `capture()` to `(event: str, **kwargs)` — only
# 1 positional arg allowed — so every telemetry event fails with
# `capture() takes 1 positional argument but 3 were given`. chromadb already
# wraps the call in try/except and just logs the failure, but the noise is
# visible in every uvicorn / `python -m ingest` startup. We monkey-patch
# `_direct_capture` to use the new signature; the patch is idempotent so
# re-running app startup (e.g. uvicorn --reload) is safe.
import posthog  # noqa: E402
import chromadb.telemetry.product.posthog as _chroma_posthog  # noqa: E402

if not getattr(_chroma_posthog.Posthog, "_AICounselor_patched", False):
    _orig_direct_capture = _chroma_posthog.Posthog._direct_capture
    _POSTHOG_EVENT_SETTINGS = _chroma_posthog.POSTHOG_EVENT_SETTINGS

    def _patched_direct_capture(self, event):  # type: ignore[no-redef]
        try:
            posthog.capture(
                event.name,
                distinct_id=self.user_id,
                properties={
                    **event.properties,
                    **_POSTHOG_EVENT_SETTINGS,
                    **self.context,
                },
            )
        except Exception as exc:
            _chroma_posthog.logger.error(
                f"Failed to send telemetry event {event.name}: {exc}"
            )

    _chroma_posthog.Posthog._direct_capture = _patched_direct_capture
    _chroma_posthog.Posthog._AICounselor_patched = True

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

    Per `app/admin/settings.py::REQUIRES_RESTART`, only `paths.*` and
    `embedding.model` are truly restart-required. `paths` is intentionally
    not applied here — chroma collection name / data dir cannot change
    in-place without rebuilding the collection. `embedding.model` IS
    applied; the SentenceTransformer instance in `rag/embeddings.py`
    will rebuild on first use after a process restart because the cached
    instance lives in the worker process only.
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
