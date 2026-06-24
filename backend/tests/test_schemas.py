"""Unit tests for Pydantic schema validation.

Covers boundary-value validation for the request models used across the
knowledge graph, room, and interaction endpoints. No database is required.
"""

import pytest
from pydantic import ValidationError

from app.schemas import (
    InteractionCreate,
    KnowledgeEdgeCreate,
    KnowledgeNodeCreate,
    RoomCreate,
)

# --- KnowledgeNodeCreate -------------------------------------------------


def test_knowledge_node_create_valid_with_defaults():
    node = KnowledgeNodeCreate(name="一元一次方程")
    assert node.name == "一元一次方程"
    assert node.threshold == 0.8  # default


def test_knowledge_node_create_empty_name_fails():
    with pytest.raises(ValidationError):
        KnowledgeNodeCreate(name="")


def test_knowledge_node_create_threshold_above_one_fails():
    with pytest.raises(ValidationError):
        KnowledgeNodeCreate(name="x", threshold=1.5)


def test_knowledge_node_create_threshold_below_zero_fails():
    with pytest.raises(ValidationError):
        KnowledgeNodeCreate(name="x", threshold=-0.1)


def test_knowledge_node_create_threshold_boundaries_valid():
    assert KnowledgeNodeCreate(name="x", threshold=0.0).threshold == 0.0
    assert KnowledgeNodeCreate(name="x", threshold=1.0).threshold == 1.0


# --- KnowledgeEdgeCreate -------------------------------------------------


def test_knowledge_edge_create_valid_with_default_relation():
    edge = KnowledgeEdgeCreate(source_id="src-1", target_id="tgt-1")
    assert edge.source_id == "src-1"
    assert edge.target_id == "tgt-1"
    assert edge.relation == "prerequisite"  # default


def test_knowledge_edge_create_empty_source_id_fails():
    with pytest.raises(ValidationError):
        KnowledgeEdgeCreate(source_id="", target_id="tgt-1")


def test_knowledge_edge_create_empty_target_id_fails():
    with pytest.raises(ValidationError):
        KnowledgeEdgeCreate(source_id="src-1", target_id="")


# --- RoomCreate ----------------------------------------------------------


def test_room_create_title_at_max_length_valid():
    title = "x" * 255
    room = RoomCreate(title=title)
    assert room.title == title


def test_room_create_title_too_long_fails():
    with pytest.raises(ValidationError):
        RoomCreate(title="x" * 256)


def test_room_create_allows_empty_title():
    # title is Optional, so omitting it is valid.
    room = RoomCreate()
    assert room.title is None


# --- InteractionCreate ---------------------------------------------------


def test_interaction_create_valid_minimal():
    inter = InteractionCreate(course_id="course-1")
    assert inter.course_id == "course-1"
    assert inter.help_count == 0  # default
    assert inter.is_correct is None


def test_interaction_create_empty_course_id_fails():
    with pytest.raises(ValidationError):
        InteractionCreate(course_id="")


def test_interaction_create_negative_help_count_fails():
    with pytest.raises(ValidationError):
        InteractionCreate(course_id="c1", help_count=-1)


def test_interaction_create_zero_help_count_valid():
    assert InteractionCreate(course_id="c1", help_count=0).help_count == 0


def test_interaction_create_negative_video_timestamp_fails():
    with pytest.raises(ValidationError):
        InteractionCreate(course_id="c1", video_timestamp=-1.0)


def test_interaction_create_zero_video_timestamp_valid():
    assert InteractionCreate(course_id="c1", video_timestamp=0.0).video_timestamp == 0.0


def test_interaction_create_negative_watch_seconds_fails():
    with pytest.raises(ValidationError):
        InteractionCreate(course_id="c1", watch_seconds=-5.0)


def test_interaction_create_zero_watch_seconds_valid():
    assert InteractionCreate(course_id="c1", watch_seconds=0.0).watch_seconds == 0.0


def test_interaction_create_empty_user_id_fails():
    # user_id is Optional but has min_length=1, so an explicit empty string fails.
    with pytest.raises(ValidationError):
        InteractionCreate(course_id="c1", user_id="")
