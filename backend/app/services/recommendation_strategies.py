"""Pluggable recommendation strategies."""

from abc import ABC, abstractmethod
from typing import Any


class RecommendationStrategy(ABC):
    """Abstract base for adaptive recommendation strategies."""

    name: str = "abstract"

    @abstractmethod
    def rank(
        self,
        candidates: list[dict[str, Any]],
        mastery_by_node: dict[str, dict[str, Any]],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Rank candidate nodes and return ordered list (best first)."""
        return candidates


class MasteryGapStrategy(RecommendationStrategy):
    """Recommend nodes with the largest mastery gap first."""

    name = "mastery_gap"

    def rank(
        self,
        candidates: list[dict[str, Any]],
        mastery_by_node: dict[str, dict[str, Any]],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        def score(node: dict[str, Any]) -> float:
            mastery = mastery_by_node.get(node["id"], {})
            threshold = mastery.get("threshold", 0.8)
            p_known = mastery.get("p_known", 0.0)
            return threshold - p_known

        return sorted(candidates, key=score, reverse=True)


class BalancedStrategy(RecommendationStrategy):
    """Balance mastery gap and prerequisite depth.

    The docstring previously advertised a "difficulty" factor, but no
    difficulty signal is available yet, so the strategy only combines the
    mastery gap (how far the learner is from the threshold) with the
    prerequisite depth (shallower nodes are preferred so foundational topics
    are tackled first). The two weights default to 0.6 / 0.4 so they sum to
    1.0; a ``difficulty_weight`` slot is reserved for when a difficulty
    estimate becomes available.
    """

    name = "balanced"

    def __init__(
        self,
        gap_weight: float = 0.6,
        depth_weight: float = 0.4,
        difficulty_weight: float = 0.0,
    ):
        # Ensure the active weights sum to 1.0 so scores stay normalised.
        total = gap_weight + depth_weight + difficulty_weight
        if total <= 0:
            gap_weight, depth_weight, difficulty_weight = 0.6, 0.4, 0.0
            total = 1.0
        self.gap_weight = gap_weight / total
        self.depth_weight = depth_weight / total
        self.difficulty_weight = difficulty_weight / total

    def rank(
        self,
        candidates: list[dict[str, Any]],
        mastery_by_node: dict[str, dict[str, Any]],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        depth_map = context.get("depth_map", {})
        max_depth = max(depth_map.values(), default=1) or 1

        def score(node: dict[str, Any]) -> float:
            mastery = mastery_by_node.get(node["id"], {})
            threshold = mastery.get("threshold", 0.8)
            p_known = mastery.get("p_known", 0.0)
            gap = threshold - p_known
            depth = depth_map.get(node["id"], 0) / max_depth
            return self.gap_weight * gap + self.depth_weight * (1 - depth)

        return sorted(candidates, key=score, reverse=True)


_STRATEGY_REGISTRY: dict[str, type[RecommendationStrategy]] = {
    MasteryGapStrategy.name: MasteryGapStrategy,
    BalancedStrategy.name: BalancedStrategy,
}


def register_strategy(name: str, cls: type[RecommendationStrategy]) -> None:
    """Register a new recommendation strategy."""
    _STRATEGY_REGISTRY[name] = cls


def get_strategy(name: str, **kwargs: Any) -> RecommendationStrategy:
    """Factory to instantiate a registered strategy."""
    if name not in _STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}")
    return _STRATEGY_REGISTRY[name](**kwargs)
