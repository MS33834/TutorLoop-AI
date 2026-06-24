"""Socratic teaching agent.

Instead of giving direct answers, this agent generates guided questions that
help the student reason toward the answer themselves. The guidance is adapted
to the student's current mastery level on the relevant knowledge node:

- Low mastery (p_known < 0.4): concrete hints, analogies, break the problem
  into smaller steps.
- Medium mastery (0.4 <= p_known < 0.8): targeted questions that point to
  the missing concept without revealing the answer.
- High mastery (p_known >= 0.8): challenge questions, edge cases, extensions.

The agent wraps the RAG context with a Socratic system prompt and delegates
the actual generation to the AI gateway.
"""

import logging
from typing import Any

from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.models.db import KnowledgeNode, Mastery

logger = logging.getLogger(__name__)

# Mastery bands that determine the Socratic prompt strategy.
MASTERY_LOW = 0.4
MASTERY_HIGH = 0.8

_BASE_PROMPT = (
    "你是一位苏格拉底式导师。你的目标不是直接给出答案，而是通过提问引导学生"
    "自己思考并发现答案。请根据学生的当前掌握程度调整引导策略。"
)

_PROMPT_BY_BAND = {
    "low": (
        "该学生对这个知识点掌握较弱。请：\n"
        "1. 用一个贴近生活的类比解释核心概念\n"
        "2. 把问题拆解成 2-3 个简单的小步骤\n"
        "3. 每一步用一个引导式提问帮助学生推进\n"
        "4. 避免一次给出全部信息"
    ),
    "medium": (
        "该学生对这个知识点有部分掌握。请：\n"
        "1. 指出他思路中可能缺失或混淆的那一个关键点\n"
        "2. 用一个针对性的提问引导他补全这个缺口\n"
        "3. 不要重复他已经掌握的部分"
    ),
    "high": (
        "该学生已较好掌握这个知识点。请：\n"
        "1. 提出一个更有挑战性的延伸问题或边界情况\n"
        "2. 鼓励他思考这个概念与其他知识的联系\n"
        "3. 引导他反思解法的局限或优化空间"
    ),
}


def _band_for_mastery(p_known: float | None) -> str:
    """Map a mastery probability to a Socratic guidance band."""
    if p_known is None:
        return "medium"
    if p_known < MASTERY_LOW:
        return "low"
    if p_known < MASTERY_HIGH:
        return "medium"
    return "high"


async def fetch_mastery_for_node(
    user_id: str | None, node_id: str | None
) -> float | None:
    """Return the student's p_known for a knowledge node, or None if unknown."""
    if not user_id or not node_id:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Mastery.p_known).where(
                Mastery.user_id == user_id, Mastery.node_id == node_id
            )
        )
        return result.scalar_one_or_none()


async def fetch_mastery_for_course(
    user_id: str | None, course_id: str
) -> float | None:
    """Return the average p_known across all nodes in a course for the user."""
    if not user_id:
        return None
    async with AsyncSessionLocal() as session:
        node_ids = (
            await session.execute(
                select(KnowledgeNode.id).where(KnowledgeNode.course_id == course_id)
            )
        ).scalars().all()
        if not node_ids:
            return None
        result = await session.execute(
            select(Mastery.p_known).where(
                Mastery.user_id == user_id, Mastery.node_id.in_(node_ids)
            )
        )
        values = [r for r in result.scalars().all() if r is not None]
        if not values:
            return None
        return sum(values) / len(values)


def build_socratic_system_prompt(
    p_known: float | None,
    context_text: str | None = None,
    node_name: str | None = None,
) -> str:
    """Build the Socratic system prompt adapted to the student's mastery.

    Args:
        p_known: The student's mastery probability on the relevant node.
        context_text: Optional RAG context (frames, knowledge nodes) to inject.
        node_name: Optional name of the most relevant knowledge node.
    """
    band = _band_for_mastery(p_known)
    parts = [_BASE_PROMPT, "", _PROMPT_BY_BAND[band]]
    if node_name:
        parts.append(f"\n当前相关知识点：{node_name}（掌握度 {p_known if p_known is not None else '未知'}）")
    if context_text:
        parts.append("")
        parts.append(context_text)
    return "\n".join(parts)


async def build_socratic_messages(
    messages: list[dict[str, Any]],
    user_id: str | None,
    course_id: str | None,
    node_id: str | None,
    context_text: str | None = None,
    node_name: str | None = None,
) -> list[dict[str, Any]]:
    """Prepend a Socratic system prompt to the user's messages.

    Looks up the student's mastery (node-level first, then course average) to
    select the appropriate guidance band, then builds the system message.
    """
    p_known: float | None = None
    if node_id:
        p_known = await fetch_mastery_for_node(user_id, node_id)
    if p_known is None and course_id:
        p_known = await fetch_mastery_for_course(user_id, course_id)

    system_prompt = build_socratic_system_prompt(
        p_known=p_known, context_text=context_text, node_name=node_name
    )
    return [{"role": "system", "content": system_prompt}, *messages]
