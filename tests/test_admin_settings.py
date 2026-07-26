"""Tests for app/admin/settings.py — section config + validation."""
from __future__ import annotations

import pytest

from app.admin.settings import (
    DEFAULTS,
    InvalidFieldError,
    REQUIRES_RESTART,
    SECTIONS,
    SettingsError,
    UnknownSectionError,
    get_effective_settings,
    update_settings,
)
from storage import admin_db
from storage.admin_db import reset_for_tests, settings as db_settings


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_db, "ADMIN_DB_PATH", str(tmp_path / "admin.db"))
    reset_for_tests()
    admin_db.init()
    yield
    reset_for_tests()


# ----- constants -----

def test_sections_are_the_four_expected():
    assert set(SECTIONS) == {"llm", "retrieval", "paths", "embedding"}


def test_defaults_contain_every_field():
    assert set(DEFAULTS["llm"].keys()) == {
        "base_url", "model_name", "temperature", "max_tokens", "timeout",
        "top_p", "frequency_penalty", "presence_penalty",
    }
    assert set(DEFAULTS["retrieval"].keys()) == {"k", "chunk_size", "chunk_overlap"}
    assert set(DEFAULTS["paths"].keys()) == {
        "documents_dir", "data_dir", "chroma_collection",
    }
    assert set(DEFAULTS["embedding"].keys()) == {"model"}


def test_requires_restart_lists_known_fields():
    assert "base_url" in REQUIRES_RESTART["llm"]
    assert "model_name" in REQUIRES_RESTART["llm"]
    assert "documents_dir" in REQUIRES_RESTART["paths"]
    assert "model" in REQUIRES_RESTART["embedding"]


# ----- get_effective_settings -----

def test_effective_returns_all_sections_with_defaults_when_db_empty():
    eff = get_effective_settings()
    assert set(eff.keys()) == {"llm", "retrieval", "paths", "embedding"}
    assert eff["llm"]["temperature"] == DEFAULTS["llm"]["temperature"]


def test_effective_merges_db_overrides_with_defaults():
    update_settings(sections={"llm": {"temperature": 0.7}}, by_username="admin")
    eff = get_effective_settings()
    assert eff["llm"]["temperature"] == 0.7
    # Other llm fields still come from defaults.
    assert eff["llm"]["max_tokens"] == DEFAULTS["llm"]["max_tokens"]


# ----- update_settings validation -----

def test_update_unknown_section_raises():
    with pytest.raises(UnknownSectionError):
        update_settings(sections={"bogus": {"x": 1}}, by_username="admin")


def test_update_llm_temperature_out_of_range():
    with pytest.raises(InvalidFieldError) as ei:
        update_settings(sections={"llm": {"temperature": 3.0}}, by_username="admin")
    assert "temperature" in str(ei.value)


def test_update_llm_max_tokens_must_be_int():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": "abc"}}, by_username="admin")


def test_update_llm_max_tokens_zero_rejected():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": 0}}, by_username="admin")


def test_update_llm_max_tokens_too_large_rejected():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"max_tokens": 99999}}, by_username="admin")


def test_update_retrieval_k_must_be_positive_int():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"retrieval": {"k": 0}}, by_username="admin")


def test_update_retrieval_k_too_large():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"retrieval": {"k": 100}}, by_username="admin")


def test_update_retrieval_chunk_overlap_must_be_less_than_chunk_size():
    update_settings(
        sections={"retrieval": {"chunk_size": 100, "chunk_overlap": 50}},
        by_username="admin",
    )
    with pytest.raises(InvalidFieldError):
        update_settings(
            sections={"retrieval": {"chunk_size": 100, "chunk_overlap": 100}},
            by_username="admin",
        )


def test_update_embedding_model_must_be_string():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"embedding": {"model": 123}}, by_username="admin")


def test_update_paths_dir_must_be_string():
    with pytest.raises(InvalidFieldError):
        update_settings(
            sections={"paths": {"documents_dir": 123}}, by_username="admin"
        )


def test_update_unknown_field_in_section_raises():
    with pytest.raises(InvalidFieldError):
        update_settings(sections={"llm": {"nonexistent": 1}}, by_username="admin")


# ----- successful updates -----

def test_update_writes_to_db_and_returns_new_value():
    new, restart = update_settings(
        sections={"llm": {"temperature": 0.5}}, by_username="admin"
    )
    assert new["llm"]["temperature"] == 0.5
    assert restart == []  # temperature is hot-reload


def test_update_returns_restart_required_fields():
    new, restart = update_settings(
        sections={"llm": {"base_url": "http://x:1234/v1"}}, by_username="admin"
    )
    assert "llm.base_url" in restart


def test_update_overwrites_previous_section_value():
    update_settings(sections={"llm": {"temperature": 0.5}}, by_username="admin")
    update_settings(
        sections={"llm": {"temperature": 0.9, "max_tokens": 1024}},
        by_username="admin",
    )
    stored = db_settings.get("llm")
    assert stored == {"temperature": 0.9, "max_tokens": 1024}


def test_update_multiple_sections_at_once():
    new, restart = update_settings(
        sections={
            "llm": {"temperature": 0.5},
            "retrieval": {"k": 10},
        },
        by_username="admin",
    )
    assert new["llm"]["temperature"] == 0.5
    assert new["retrieval"]["k"] == 10
    assert restart == []


def test_multi_section_update_is_atomic_on_validation_failure():
    # Pre-condition: empty DB.
    assert db_settings.get_all() == {}
    # First section is valid, second is out of range.
    with pytest.raises(InvalidFieldError):
        update_settings(
            sections={
                "llm": {"temperature": 0.5},
                "retrieval": {"k": 999},
            },
            by_username="admin",
        )
    # No row was persisted for either section.
    assert db_settings.get_all() == {}


def test_partial_update_preserves_other_fields():
    update_settings(sections={"llm": {"temperature": 0.5}}, by_username="admin")
    update_settings(sections={"llm": {"max_tokens": 4096}}, by_username="admin")
    stored = db_settings.get("llm")
    assert stored["temperature"] == 0.5
    assert stored["max_tokens"] == 4096