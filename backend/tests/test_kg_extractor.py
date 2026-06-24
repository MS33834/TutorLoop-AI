"""Unit tests for knowledge graph parsing helpers."""


from app.services.kg_extractor import _extract_json_object, _normalize_graph, _repair_truncated_json


def test_normalize_graph_fills_defaults():
    raw = {
        "nodes": [
            {"id": "n1", "name": "导数", "description": "变化率", "threshold": 0.85},
            {"id": "n2", "name": "极限"}
        ],
        "edges": [
            {"from": "n2", "to": "n1", "relation": "prerequisite"}
        ]
    }
    graph = _normalize_graph(raw)
    assert len(graph["nodes"]) == 2
    assert graph["nodes"][1]["description"] == "极限"
    assert graph["nodes"][1]["threshold"] == 0.8
    assert graph["edges"][0]["relation"] == "prerequisite"


def test_normalize_graph_filters_invalid_edges():
    raw = {
        "nodes": [{"id": "n1", "name": "A"}],
        "edges": [
            {"from": "n1", "to": "missing", "relation": "requires"}
        ]
    }
    graph = _normalize_graph(raw)
    assert len(graph["nodes"]) == 1
    assert graph["edges"] == []


def test_normalize_graph_returns_empty_when_no_nodes():
    graph = _normalize_graph({"nodes": [], "edges": []})
    assert graph["nodes"] == []
    assert graph["edges"] == []


def test_extract_json_object_strips_markdown_fences():
    text = '```json\n{"nodes": []}\n```'
    assert _extract_json_object(text) == '{"nodes": []}'


def test_repair_truncated_json_closes_braces():
    truncated = '{"nodes": [{"id": "n1"'
    repaired = _repair_truncated_json(truncated)
    # Should at least be valid JSON now
    import json
    assert isinstance(json.loads(repaired), dict)
