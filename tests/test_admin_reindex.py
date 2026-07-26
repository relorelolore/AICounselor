"""Tests for app/admin/reindex.py — wraps ingest.indexer.build_index."""
from __future__ import annotations

import threading
import time

import pytest

from app.admin import reindex
from app.admin.reindex import ReindexBusyError, get_last_reindex, run_reindex
from storage import admin_db
from storage.admin_db import reset_for_tests


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


@pytest.fixture
def fake_build_index(monkeypatch):
    """Patch ingest.indexer.build_index; returns the captured list."""
    captured = {}

    def _impl(*, force: bool = False):
        captured["force"] = force
        captured["calls"] = captured.get("calls", 0) + 1
        # Simulate slow work so a second concurrent call would overlap.
        time.sleep(0.05)
        return {
            "added": 3,
            "skipped": 1,
            "failed": [],
            "items": [
                {"status": "added", "path": "/a.pdf", "chunks": 10},
                {"status": "added", "path": "/b.pdf", "chunks": 5},
                {"status": "skipped", "path": "/c.pdf", "reason": "unchanged"},
                {"status": "added", "path": "/d.pdf", "chunks": 2},
            ],
            "meta_written": True,
        }

    monkeypatch.setattr("app.admin.reindex.build_index", _impl)
    return captured


def test_run_reindex_returns_result(fake_build_index):
    result = run_reindex(force=False)
    assert result["added"] == 3
    assert result["skipped"] == 1
    assert fake_build_index["force"] is False
    assert fake_build_index["calls"] == 1


def test_run_reindex_passes_force_flag(fake_build_index):
    run_reindex(force=True)
    assert fake_build_index["force"] is True


def test_run_reindex_persists_last_to_kv(fake_build_index):
    run_reindex(force=True)
    last = get_last_reindex()
    assert last is not None
    assert last["force"] is True
    assert last["added"] == 3
    assert last["skipped"] == 1
    assert "ts" in last
    assert "items" not in last  # truncated to summary only


def test_get_last_reindex_returns_none_before_any_run():
    assert get_last_reindex() is None


def test_concurrent_runs_second_raises_busy(fake_build_index):
    """Hold the lock manually while calling run_reindex."""
    reindex._REINDEX_LOCK.acquire()
    try:
        with pytest.raises(ReindexBusyError):
            run_reindex()
    finally:
        reindex._REINDEX_LOCK.release()


def test_concurrent_runs_in_threads_one_busy_one_ok(fake_build_index, monkeypatch):
    """Two threads: first holds lock for 100ms; second gets busy."""
    results = {}

    def call():
        try:
            results["value"] = run_reindex()
        except ReindexBusyError:
            results["error"] = "busy"

    t1 = threading.Thread(target=call)
    t1.start()
    time.sleep(0.02)
    # While t1 is running the slow fake build, a second call gets busy.
    with pytest.raises(ReindexBusyError):
        run_reindex()
    t1.join()
    assert "value" in results
    assert results["value"]["added"] == 3
