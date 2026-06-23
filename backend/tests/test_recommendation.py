"""Unit tests for recommendation helpers."""

import math

from app.services.recommendation import (
    _build_prereq_map,
    _compute_depth,
    _cosine_similarity,
    _text_overlap_score,
)


def test_cosine_similarity_orthogonal():
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_identical():
    assert math.isclose(_cosine_similarity([1.0, 1.0], [1.0, 1.0]), 1.0)


def test_cosine_similarity_empty_vectors():
    assert _cosine_similarity([], [1.0, 0.0]) == 0.0
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_text_overlap_score_basic():
    assert math.isclose(_text_overlap_score("hello world", "hello there"), 0.5)


def test_text_overlap_score_no_overlap():
    assert _text_overlap_score("foo bar", "baz qux") == 0.0


def test_text_overlap_score_empty_query():
    assert _text_overlap_score("", "some text") == 0.0


def test_build_prereq_map_ignores_non_prerequisite():
    edges = [
        {"from": "a", "to": "b", "relation": "prerequisite"},
        {"from": "b", "to": "c", "relation": "related"},
    ]
    prereqs = _build_prereq_map(edges)
    assert prereqs == {"b": {"a"}}


def test_build_prereq_map_ignores_self_loops():
    edges = [
        {"from": "a", "to": "a", "relation": "prerequisite"},
        {"from": "a", "to": "b", "relation": "prerequisite"},
    ]
    prereqs = _build_prereq_map(edges)
    assert prereqs == {"b": {"a"}}


def test_compute_depth_linear_chain():
    edges = [
        {"from": "a", "to": "b", "relation": "prerequisite"},
        {"from": "b", "to": "c", "relation": "prerequisite"},
    ]
    depth = _compute_depth(_build_prereq_map(edges))
    # Depth is 1-based: node with no prerequisites has depth 1.
    assert depth["a"] == 1
    assert depth["b"] == 2
    assert depth["c"] == 3


def test_compute_depth_handles_cycle():
    edges = [
        {"from": "a", "to": "b", "relation": "prerequisite"},
        {"from": "b", "to": "a", "relation": "prerequisite"},
    ]
    depth = _compute_depth(_build_prereq_map(edges))
    # Cycle guard should prevent infinite recursion.
    assert "a" in depth
    assert "b" in depth
