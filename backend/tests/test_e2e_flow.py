"""End-to-end integration tests for the TutorLoop-AI backend API layer.

These tests exercise the full FastAPI stack (routing, auth, DB, services) against
a real PostgreSQL+pgvector backend. They are skipped automatically when PG is not
reachable (local sandbox without Docker); on CI the pgvector service container
makes them run.

Each test is self-contained: it creates its own course / video / nodes / room via
the API and the shared ``auth_headers`` fixture, so test ordering does not matter.
"""

import uuid

import pytest

# Module-level skip guard: if PG is not available, skip the entire module
# without collecting fixtures (which require the event loop / DB). The fixture
# ``skip_without_pg`` below is the per-test guard referenced by the task spec;
# both layers exist so a stray ``pytestmark`` interaction can't silently run a
# test against a missing DB.
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("skip_without_pg"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_course(async_client, auth_headers, title: str = "E2E Course") -> str:
    resp = await async_client.post(
        "/api/courses",
        json={"title": f"{title}-{uuid.uuid4().hex[:6]}", "description": "e2e"},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


# Minimal fake MP4 byte stream that passes the upload route's magic-byte check
# (bytes[4:8] == b"ftyp" for .mp4/.mov). Padded well past the 12-byte minimum.
_FAKE_MP4 = b"\x00\x00\x00\x08ftypisom" + b"\x00" * 256


# ---------------------------------------------------------------------------
# 1. Auth: register → /me
# ---------------------------------------------------------------------------

async def test_register_login_me(async_client, auth_headers):
    """Register a fresh user and verify /api/auth/me returns its username."""
    username = f"e2e_me_{uuid.uuid4().hex[:6]}"
    resp = await async_client.post(
        "/api/auth/register",
        json={"username": username, "password": "Test1234!"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    me_resp = await async_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200, me_resp.text
    body = me_resp.json()
    assert body["username"] == username


# ---------------------------------------------------------------------------
# 2. Course creation
# ---------------------------------------------------------------------------

async def test_create_course(async_client, auth_headers):
    """POST /api/courses returns id + title for the created course."""
    title = f"E2E Course-{uuid.uuid4().hex[:6]}"
    resp = await async_client.post(
        "/api/courses",
        json={"title": title, "description": "created by e2e"},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["id"]
    assert body["title"] == title


# ---------------------------------------------------------------------------
# 3. Video upload (process_video mocked)
# ---------------------------------------------------------------------------

async def test_upload_video(async_client, auth_headers, monkeypatch):
    """POST /api/courses/{id}/videos accepts a fake MP4 stream and returns video_id.

    ``process_video`` is patched on the courses router module (where it was bound
    at import time) so the sync fallback path doesn't try to run opencv.
    """
    from app.routers import courses as courses_router

    async def _fake_process(course_id, title, source_path, video_id=None):
        return video_id or "fake-video-id", []

    monkeypatch.setattr(courses_router, "process_video", _fake_process)

    course_id = await _create_course(async_client, auth_headers, title="Video Course")
    resp = await async_client.post(
        f"/api/courses/{course_id}/videos",
        files={"file": ("clip.mp4", _FAKE_MP4, "video/mp4")},
        data={"title": "Clip"},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["video_id"]
    assert body["title"] == "Clip"


# ---------------------------------------------------------------------------
# 4. Knowledge graph: nodes + edges + GET graph
# ---------------------------------------------------------------------------

async def test_create_nodes_and_edges(async_client, auth_headers):
    """Create 2 nodes, 1 edge between them, then GET the graph to verify."""
    course_id = await _create_course(async_client, auth_headers, title="Graph Course")

    node_a = await async_client.post(
        f"/api/courses/{course_id}/nodes",
        json={"name": "NodeA", "description": "first", "threshold": 0.8},
        headers=auth_headers,
    )
    assert node_a.status_code in (200, 201), node_a.text
    node_a_id = node_a.json()["id"]

    node_b = await async_client.post(
        f"/api/courses/{course_id}/nodes",
        json={"name": "NodeB", "description": "second", "threshold": 0.7},
        headers=auth_headers,
    )
    assert node_b.status_code in (200, 201), node_b.text
    node_b_id = node_b.json()["id"]

    edge = await async_client.post(
        f"/api/courses/{course_id}/edges",
        json={"source_id": node_a_id, "target_id": node_b_id, "relation": "prerequisite"},
        headers=auth_headers,
    )
    assert edge.status_code in (200, 201), edge.text

    graph = await async_client.get(f"/api/courses/{course_id}/graph")
    assert graph.status_code == 200, graph.text
    g = graph.json()
    assert len(g["nodes"]) == 2
    assert len(g["edges"]) == 1
    assert {n["name"] for n in g["nodes"]} == {"NodeA", "NodeB"}
    assert g["edges"][0]["from"] == node_a_id
    assert g["edges"][0]["to"] == node_b_id


# ---------------------------------------------------------------------------
# 5. Room create → get session token → join (entry_count increments)
# ---------------------------------------------------------------------------

async def test_create_room_and_join(async_client, auth_headers):
    """POST room → GET /api/rooms/{slug} (session_token) → POST join; entry_count=1."""
    course_id = await _create_course(async_client, auth_headers, title="Room Course")

    create = await async_client.post(
        f"/api/courses/{course_id}/rooms",
        json={"title": "E2E Room", "allow_anonymous": True},
        headers=auth_headers,
    )
    assert create.status_code in (200, 201), create.text
    slug = create.json()["slug"]

    pub = await async_client.get(f"/api/rooms/{slug}")
    assert pub.status_code == 200, pub.text
    session_token = pub.json().get("session_token")
    assert session_token, "GET /api/rooms/{slug} must issue a signed session_token"

    join = await async_client.post(
        f"/api/rooms/{slug}/join",
        json={"session_id": session_token},
    )
    assert join.status_code == 200, join.text

    # join_room returns RoomPublicResponse (no entry_count); verify via the
    # owner's room-list endpoint which returns RoomResponse with entry_count.
    rooms = await async_client.get(
        f"/api/courses/{course_id}/rooms",
        headers=auth_headers,
    )
    assert rooms.status_code == 200, rooms.text
    target = next(r for r in rooms.json() if r["slug"] == slug)
    assert target["entry_count"] == 1


# ---------------------------------------------------------------------------
# 6. Chat SSE streaming
# ---------------------------------------------------------------------------

async def test_chat_sse(async_client, auth_headers):
    """POST /api/chat streams SSE: token chunks followed by a [DONE] sentinel."""
    course_id = await _create_course(async_client, auth_headers, title="Chat Course")
    create = await async_client.post(
        f"/api/courses/{course_id}/rooms",
        json={"title": "Chat Room", "allow_anonymous": True},
        headers=auth_headers,
    )
    slug = create.json()["slug"]

    token_chunks: list[str] = []
    saw_done = False
    async with async_client.stream(
        "POST",
        "/api/chat",
        json={
            "messages": [{"role": "user", "content": "你好"}],
            "room_slug": slug,
        },
        headers=auth_headers,
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload == "[DONE]":
                saw_done = True
                break
            # Token chunks are JSON dicts like {"type":"token","content":"..."}
            # (the gateway mock yields {"type":"token","content":...}). Any
            # non-[DONE] data line counts as a streamed token event.
            token_chunks.append(payload)

    assert token_chunks, "expected at least one token chunk before [DONE]"
    assert saw_done, "expected the SSE stream to terminate with data: [DONE]"


# ---------------------------------------------------------------------------
# 7. Video progress sync (PUT then GET)
# ---------------------------------------------------------------------------

async def test_video_progress_sync(async_client, auth_headers, monkeypatch):
    """PUT progress → GET progress returns the persisted position_seconds."""
    from app.routers import courses as courses_router

    captured_video_id: dict[str, str] = {}

    async def _fake_process(course_id, title, source_path, video_id=None):
        captured_video_id["v"] = video_id or "fallback-vid"
        return video_id or "fallback-vid", []

    monkeypatch.setattr(courses_router, "process_video", _fake_process)

    course_id = await _create_course(async_client, auth_headers, title="Progress Course")
    up = await async_client.post(
        f"/api/courses/{course_id}/videos",
        files={"file": ("clip.mp4", _FAKE_MP4, "video/mp4")},
        data={"title": "Progress Clip"},
        headers=auth_headers,
    )
    assert up.status_code in (200, 201), up.text
    video_id = up.json()["video_id"]

    put_resp = await async_client.put(
        f"/api/users/me/videos/{video_id}/progress",
        json={"position_seconds": 42.5, "watched_seconds": 10.0, "video_id": video_id},
        headers=auth_headers,
    )
    assert put_resp.status_code == 200, put_resp.text

    get_resp = await async_client.get(
        f"/api/users/me/videos/{video_id}/progress",
        headers=auth_headers,
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["position_seconds"] == 42.5


# ---------------------------------------------------------------------------
# 8. Mastery + recommendation shape
# ---------------------------------------------------------------------------

async def test_mastery_and_recommend(async_client, auth_headers):
    """GET mastery + GET recommend both return 200 with the documented shape."""
    course_id = await _create_course(async_client, auth_headers, title="Mastery Course")

    mastery = await async_client.get(
        "/api/users/me/mastery",
        params={"course_id": course_id},
        headers=auth_headers,
    )
    assert mastery.status_code == 200, mastery.text
    assert isinstance(mastery.json(), list)

    recommend = await async_client.get(
        "/api/users/me/recommend",
        params={"course_id": course_id},
        headers=auth_headers,
    )
    assert recommend.status_code == 200, recommend.text
    rec_body = recommend.json()
    # RecommendationResponse: {recommendation: dict|None, message: str|None}
    assert "recommendation" in rec_body


# ---------------------------------------------------------------------------
# 9. Report / timeline / question-distribution
# ---------------------------------------------------------------------------

async def test_report_timeline_distribution(async_client, auth_headers):
    """GET report + timeline + question-distribution all return 200."""
    course_id = await _create_course(async_client, auth_headers, title="Report Course")

    report = await async_client.get(
        "/api/users/me/report",
        params={"course_id": course_id},
        headers=auth_headers,
    )
    assert report.status_code == 200, report.text
    assert report.json()["course_id"] == course_id

    timeline = await async_client.get(
        "/api/users/me/timeline",
        params={"course_id": course_id},
        headers=auth_headers,
    )
    assert timeline.status_code == 200, timeline.text
    assert "daily_activity" in timeline.json()

    dist = await async_client.get(
        "/api/users/me/question-distribution",
        headers=auth_headers,
    )
    assert dist.status_code == 200, dist.text
    assert "distribution" in dist.json()


# ---------------------------------------------------------------------------
# 10. Room leave (entry_count decrements)
# ---------------------------------------------------------------------------

async def test_room_leave(async_client, auth_headers):
    """POST join (entry_count=1) → POST leave (entry_count back to 0)."""
    course_id = await _create_course(async_client, auth_headers, title="Leave Course")
    create = await async_client.post(
        f"/api/courses/{course_id}/rooms",
        json={"title": "Leave Room", "allow_anonymous": True},
        headers=auth_headers,
    )
    slug = create.json()["slug"]

    pub = await async_client.get(f"/api/rooms/{slug}")
    session_token = pub.json()["session_token"]

    join = await async_client.post(
        f"/api/rooms/{slug}/join",
        json={"session_id": session_token},
    )
    assert join.status_code == 200, join.text

    leave = await async_client.post(
        f"/api/rooms/{slug}/leave",
        json={"session_id": session_token},
    )
    assert leave.status_code == 200, leave.text

    rooms = await async_client.get(
        f"/api/courses/{course_id}/rooms",
        headers=auth_headers,
    )
    target = next(r for r in rooms.json() if r["slug"] == slug)
    assert target["entry_count"] == 0
