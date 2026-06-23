"""Unit tests for class-level report aggregation helpers."""

from datetime import date, datetime, timedelta

from app.services.class_report_service import (
    _aggregate_weak_nodes,
    _class_avg_mastery,
    _fill_activity_trend,
)


def test_fill_activity_trend_completes_missing_days():
    today = date.today()
    rows = [(today, 3), (today - timedelta(days=2), 5)]
    trend = _fill_activity_trend(rows)
    assert len(trend) == 7
    assert trend[-1]["date"] == today.isoformat()
    assert trend[-1]["count"] == 3
    # Day offset 2 from today should have count 5; fill others with 0
    found_five = any(day["count"] == 5 for day in trend)
    assert found_five
    zero_days = [day for day in trend if day["count"] == 0]
    assert len(zero_days) == 5


def test_fill_activity_trend_handles_empty_input():
    trend = _fill_activity_trend([])
    assert len(trend) == 7
    assert all(day["count"] == 0 for day in trend)


def test_aggregate_weak_nodes_ranks_by_gap():
    rows = [
        ("u1", 0.9, "n1", "Node A", 0.8),  # mastered on average
        ("u2", 0.7, "n1", "Node A", 0.8),
        ("u1", 0.2, "n2", "Node B", 0.8),
        ("u2", 0.3, "n2", "Node B", 0.8),
    ]
    weak_nodes = _aggregate_weak_nodes(rows)
    assert len(weak_nodes) == 1
    node = weak_nodes[0]
    assert node["node_id"] == "n2"
    assert node["name"] == "Node B"
    assert node["avg_p_known"] == 0.25
    assert node["threshold"] == 0.8
    assert node["gap"] == 0.55
    assert node["struggling_students"] == 2


def test_aggregate_weak_nodes_ignores_mastered_nodes():
    rows = [
        ("u1", 0.85, "n1", "Node A", 0.8),
        ("u2", 0.9, "n1", "Node A", 0.8),
    ]
    weak_nodes = _aggregate_weak_nodes(rows)
    assert weak_nodes == []


def test_class_avg_mastery_computes_mean():
    rows = [
        ("u1", 0.2, "n1", "Node A", 0.8),
        ("u1", 0.8, "n2", "Node B", 0.8),
        ("u2", 0.5, "n1", "Node A", 0.8),
    ]
    assert _class_avg_mastery(rows) == 0.5


def test_class_avg_mastery_returns_zero_for_empty():
    assert _class_avg_mastery([]) == 0.0
