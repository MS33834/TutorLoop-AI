"""Unit tests for learning room helpers.

These tests cover pure helper functions in the rooms router without requiring a
running database. Integration tests for the full async CRUD flow should be added
once an in-memory/async test database fixture is available.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.rooms import (
    _generate_slug,
    _parse_expires_at,
    _serialize_public_room,
    _serialize_room,
)


def test_generate_slug_is_short_and_url_safe():
    slug = _generate_slug()
    assert len(slug) == 8
    # URL-safe alphabet used by secrets.token_urlsafe.
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    assert set(slug) <= allowed


def test_generate_slug_varies():
    slugs = {_generate_slug() for _ in range(50)}
    assert len(slugs) > 1


def test_parse_expires_at_empty_returns_none():
    assert _parse_expires_at(None) is None
    assert _parse_expires_at("") is None


def test_parse_expires_at_aware_input_preserved():
    dt = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    parsed = _parse_expires_at(dt.isoformat())
    assert parsed == dt
    assert parsed.tzinfo is not None


def test_parse_expires_at_naive_input_gets_utc():
    parsed = _parse_expires_at("2026-12-31T23:59:59")
    assert parsed.tzinfo is timezone.utc
    assert parsed.hour == 23


def test_parse_expires_at_invalid_raises_400():
    with pytest.raises(HTTPException) as exc_info:
        _parse_expires_at("not-a-datetime")
    assert exc_info.value.status_code == 400


def test_serialize_room_maps_fields():
    room = SimpleNamespace(
        id="room-id",
        slug="abc123",
        course_id="course-id",
        title="Test Room",
        allow_anonymous=True,
        is_active=True,
        expires_at=datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
        entry_count=5,
        last_activity_at=datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc),
        welcome_message="Welcome!",
        max_participants=30,
        config_json={"theme": "dark"},
        created_at=datetime(2026, 6, 22, 8, 0, 0, tzinfo=timezone.utc),
    )
    data = _serialize_room(room)
    assert data.id == "room-id"
    assert data.slug == "abc123"
    assert data.title == "Test Room"
    assert data.entry_count == 5
    assert data.welcome_message == "Welcome!"
    assert data.max_participants == 30
    assert data.config_json == {"theme": "dark"}
    assert data.expires_at.endswith("+00:00")


def test_serialize_public_room_omits_private_fields():
    room = SimpleNamespace(
        slug="abc123",
        course_id="course-id",
        title="Test Room",
        password_hash="hashed",
        allow_anonymous=True,
        is_active=True,
        expires_at=None,
    )
    data = _serialize_public_room(room)
    assert data.slug == "abc123"
    assert data.require_password is True
    assert "password_hash" not in data.model_dump()
    assert "entry_count" not in data.model_dump()
