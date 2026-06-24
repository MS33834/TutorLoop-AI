"""Unit tests for the Socratic teaching agent.

These tests cover the pure prompt-building logic (no DB / no gateway) so they
run fast and don't require external services. The async mastery-lookup helpers
are tested via monkeypatching of ``AsyncSessionLocal``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.socratic_agent import (
    MASTERY_HIGH,
    MASTERY_LOW,
    _band_for_mastery,
    build_socratic_messages,
    build_socratic_system_prompt,
    fetch_mastery_for_course,
    fetch_mastery_for_node,
)

# ---------------------------------------------------------------------------
# _band_for_mastery
# ---------------------------------------------------------------------------


def test_band_for_mastery_low():
    assert _band_for_mastery(0.1) == "low"
    assert _band_for_mastery(0.0) == "low"
    assert _band_for_mastery(MASTERY_LOW - 0.01) == "low"


def test_band_for_mastery_medium():
    assert _band_for_mastery(MASTERY_LOW) == "medium"
    assert _band_for_mastery(0.5) == "medium"
    assert _band_for_mastery(MASTERY_HIGH - 0.01) == "medium"


def test_band_for_mastery_high():
    assert _band_for_mastery(MASTERY_HIGH) == "high"
    assert _band_for_mastery(0.9) == "high"
    assert _band_for_mastery(1.0) == "high"


def test_band_for_mastery_none_defaults_to_medium():
    """When mastery is unknown, default to the medium band."""
    assert _band_for_mastery(None) == "medium"


# ---------------------------------------------------------------------------
# build_socratic_system_prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_base_prompt():
    prompt = build_socratic_system_prompt(p_known=0.5)
    assert "苏格拉底式导师" in prompt


def test_system_prompt_low_band_includes_analogy_guidance():
    prompt = build_socratic_system_prompt(p_known=0.1)
    assert "类比" in prompt
    assert "拆解" in prompt


def test_system_prompt_medium_band_includes_targeted_question():
    prompt = build_socratic_system_prompt(p_known=0.5)
    assert "缺失" in prompt or "缺口" in prompt


def test_system_prompt_high_band_includes_challenge():
    prompt = build_socratic_system_prompt(p_known=0.9)
    assert "挑战" in prompt or "延伸" in prompt


def test_system_prompt_includes_node_name_when_provided():
    prompt = build_socratic_system_prompt(p_known=0.5, node_name="二分查找")
    assert "二分查找" in prompt


def test_system_prompt_includes_context_when_provided():
    prompt = build_socratic_system_prompt(p_known=0.5, context_text="RAG上下文内容")
    assert "RAG上下文内容" in prompt


def test_system_prompt_unknown_mastery_shows_unknown_label():
    prompt = build_socratic_system_prompt(p_known=None, node_name="测试节点")
    assert "未知" in prompt


# ---------------------------------------------------------------------------
# fetch_mastery_for_node / fetch_mastery_for_course (DB-mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_mastery_for_node_returns_none_when_no_user():
    result = await fetch_mastery_for_node(None, "node-1")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_mastery_for_node_returns_none_when_no_node():
    result = await fetch_mastery_for_node("user-1", None)
    assert result is None


@pytest.mark.asyncio
async def test_fetch_mastery_for_node_queries_db():
    """Verify the helper executes a DB query and returns the scalar result."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = 0.65
    mock_session.execute.return_value = mock_result

    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.socratic_agent.AsyncSessionLocal", return_value=mock_session):
        result = await fetch_mastery_for_node("user-1", "node-1")

    assert result == 0.65
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_mastery_for_course_returns_none_when_no_user():
    result = await fetch_mastery_for_course(None, "course-1")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_mastery_for_course_returns_none_when_no_nodes():
    """If the course has no knowledge nodes, return None."""
    mock_session = AsyncMock()
    mock_node_result = MagicMock()
    mock_node_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_node_result

    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.socratic_agent.AsyncSessionLocal", return_value=mock_session):
        result = await fetch_mastery_for_course("user-1", "course-1")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_mastery_for_course_averages_values():
    """The course-level mastery is the mean of per-node p_known values."""
    mock_session = AsyncMock()

    # First execute: node ids; second execute: mastery values.
    mock_node_result = MagicMock()
    mock_node_result.scalars.return_value.all.return_value = ["n1", "n2", "n3"]

    mock_mastery_result = MagicMock()
    mock_mastery_result.scalars.return_value.all.return_value = [0.3, 0.6, 0.9]

    mock_session.execute.side_effect = [mock_node_result, mock_mastery_result]

    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.socratic_agent.AsyncSessionLocal", return_value=mock_session):
        result = await fetch_mastery_for_course("user-1", "course-1")

    assert result == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# build_socratic_messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_socratic_messages_prepends_system_message():
    """The returned list must start with a system-role message."""
    messages = [{"role": "user", "content": "什么是递归？"}]
    with (
        patch(
            "app.services.socratic_agent.fetch_mastery_for_node",
            new_callable=AsyncMock,
            return_value=0.5,
        ),
    ):
        result = await build_socratic_messages(
            messages, user_id="u1", course_id="c1", node_id="n1"
        )

    assert result[0]["role"] == "system"
    assert "苏格拉底" in result[0]["content"]
    # Original messages preserved after the system message.
    assert result[1] == messages[0]


@pytest.mark.asyncio
async def test_build_socratic_messages_falls_back_to_course_mastery():
    """When node mastery is None, fall back to course-level average."""
    messages = [{"role": "user", "content": "hi"}]
    with (
        patch(
            "app.services.socratic_agent.fetch_mastery_for_node",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.socratic_agent.fetch_mastery_for_course",
            new_callable=AsyncMock,
            return_value=0.85,
        ) as mock_course,
    ):
        result = await build_socratic_messages(
            messages, user_id="u1", course_id="c1", node_id="n1"
        )

    mock_course.assert_awaited_once_with("u1", "c1")
    # 0.85 is in the high band.
    assert "挑战" in result[0]["content"] or "延伸" in result[0]["content"]


@pytest.mark.asyncio
async def test_build_socratic_messages_no_mastery_uses_medium_band():
    """When neither node nor course mastery is available, use medium band."""
    messages = [{"role": "user", "content": "hi"}]
    with (
        patch(
            "app.services.socratic_agent.fetch_mastery_for_node",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.socratic_agent.fetch_mastery_for_course",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await build_socratic_messages(
            messages, user_id="u1", course_id="c1", node_id="n1"
        )

    # Medium band prompt mentions "缺失" or "缺口".
    assert "缺失" in result[0]["content"] or "缺口" in result[0]["content"]
