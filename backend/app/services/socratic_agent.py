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

import json
import logging
import re
from typing import Any

from sqlalchemy import select

from app.db.postgres import AsyncSessionLocal
from app.gateway import chat_completion
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


def _band_for_anonymous(text: str | None) -> str:
    """Pick a guidance band for anonymous users from question content.

    Anonymous users have no mastery history, so instead of always falling back
    to the medium band we adapt to the question: a short, focused question
    suggests the student knows what they want (high band → skip heavy guidance
    and answer more directly), while a long, complex question suggests they are
    lost (low band → more scaffolding and analogies).
    """
    if not text:
        return "medium"
    length = len(text.strip())
    if length >= 50:
        return "low"
    if length < 20:
        return "high"
    return "medium"


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
    band: str | None = None,
) -> str:
    """Build the Socratic system prompt adapted to the student's mastery.

    Args:
        p_known: The student's mastery probability on the relevant node.
        context_text: Optional RAG context (frames, knowledge nodes) to inject.
        node_name: Optional name of the most relevant knowledge node.
        band: Optional explicit guidance band override (e.g. for anonymous
            users whose band is derived from question content instead of
            mastery). When provided it takes precedence over ``p_known``.
    """
    if band is None:
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
    Anonymous users (no ``user_id``) have no mastery history, so their band is
    derived from the latest user message's length/complexity instead of
    defaulting to the static medium band.
    """
    p_known: float | None = None
    if node_id:
        p_known = await fetch_mastery_for_node(user_id, node_id)
    if p_known is None and course_id:
        p_known = await fetch_mastery_for_course(user_id, course_id)

    band: str | None = None
    if user_id is None:
        # Anonymous user: adapt the band to the question content.
        last_user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    last_user_text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            last_user_text = block.get("text", "")
                            break
                break
        band = _band_for_anonymous(last_user_text)

    system_prompt = build_socratic_system_prompt(
        p_known=p_known, context_text=context_text, node_name=node_name, band=band
    )
    return [{"role": "system", "content": system_prompt}, *messages]


_ASSESSMENT_PROMPT = (
    "你是一位严谨的教学评估助手。请根据知识点和上下文，判断学生的回答是否正确。\n"
    "输出必须是纯 JSON，不要包含任何其他解释或 markdown 代码块。格式如下：\n"
    '{"is_correct": true 或 false, "confidence": 0.0-1.0, "feedback": "简要说明判断理由"}\n'
    "如果不确定，confidence 应偏低；如果回答明显无关或空白，is_correct 为 false。"
)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences and language hints from model output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = (
            text[first_newline + 1:]
            if first_newline != -1
            else text.lstrip("`")
        )
        text = text.rstrip("`").strip()
    return text


def _extract_json_object(text: str) -> str:
    """Locate the outermost JSON object in a string."""
    text = _strip_markdown_fences(text)
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


# Keywords signalling a correct (affirmative) answer, used as a last-resort
# fallback when the LLM cannot produce an explicit correct/incorrect verdict.
_CORRECT_KEYWORDS = {"对", "正确", "是的", "没错", "yes", "right", "correct", "true", "ok"}
_INCORRECT_KEYWORDS = {"错", "不对", "错误", "不正确", "no", "wrong", "incorrect", "false"}


def _keyword_fallback(student_answer: str) -> dict[str, Any]:
    """Best-effort verdict from keyword matching when the LLM is undecided."""
    lowered = student_answer.lower()
    if any(kw in lowered for kw in _INCORRECT_KEYWORDS):
        return {"is_correct": False, "confidence": 0.3, "feedback": "无法判断回答正误（关键词回退）。"}
    if any(kw in lowered for kw in _CORRECT_KEYWORDS):
        return {"is_correct": True, "confidence": 0.3, "feedback": "无法判断回答正误（关键词回退）。"}
    # No signal either way: skip the BKT update by returning None.
    return {"is_correct": None, "confidence": 0.0, "feedback": "无法判断回答正误。"}


async def assess_answer(
    question_context: str,
    student_answer: str,
    node_name: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Use the LLM to assess whether a student's answer is correct.

    Returns a dict with ``is_correct`` (bool or None), ``confidence`` (float),
    and ``feedback`` (str). This lets the chat flow update BKT mastery without
    requiring a separate frontend action.

    ``question`` is the Socratic question the student is replying to (typically
    the previous assistant turn). Without it the LLM cannot know what the
    student is answering, so the assessment is unreliable.
    """
    if not student_answer or not student_answer.strip():
        return {"is_correct": False, "confidence": 1.0, "feedback": "回答为空。"}

    context_parts = []
    if node_name:
        context_parts.append(f"知识点：{node_name}")
    if question:
        context_parts.append(f"导师提问：{question}")
    if question_context:
        context_parts.append(question_context)
    context = "\n".join(context_parts) or "请评估以下学生回答。"

    def _build_messages(retry: bool = False) -> list[dict[str, Any]]:
        system_prompt = _ASSESSMENT_PROMPT
        if retry:
            # Reinforce that the model MUST return an explicit correct/incorrect
            # verdict rather than null when it cannot decide.
            system_prompt = (
                _ASSESSMENT_PROMPT
                + "\n\n重要：你必须明确返回 true 或 false，不允许返回 null。"
                "如果回答与问题相关且方向正确返回 true；如果无关、错误或空白返回 false。"
            )
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"{context}\n\n学生回答：{student_answer}\n\n请给出 JSON 评估结果。",
            },
        ]

    def _parse_verdict(data: dict[str, Any]) -> dict[str, Any] | None:
        is_correct = data.get("is_correct")
        if is_correct is None:
            return None
        if not isinstance(is_correct, bool):
            # Tolerate string values from less strict models.
            lowered = str(is_correct).lower()
            is_correct = lowered in {"true", "yes", "1", "正确"}
        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        feedback = str(data.get("feedback", "")).strip() or "回答已评估。"
        return {"is_correct": is_correct, "confidence": confidence, "feedback": feedback}

    # First attempt.
    try:
        response = await chat_completion(messages=_build_messages(), model_type="text")
        text = response["choices"][0]["message"].get("content", "")
        data = json.loads(_extract_json_object(text))
        verdict = _parse_verdict(data)
    except Exception as exc:
        logger.warning("Assessment parsing failed: %s", exc)
        verdict = None

    # Retry once with a stricter prompt when the model could not decide.
    if verdict is None:
        try:
            response = await chat_completion(
                messages=_build_messages(retry=True), model_type="text"
            )
            text = response["choices"][0]["message"].get("content", "")
            data = json.loads(_extract_json_object(text))
            verdict = _parse_verdict(data)
        except Exception as exc:
            logger.warning("Assessment retry parsing failed: %s", exc)
            verdict = None

    # Final keyword-based fallback so the interaction still updates BKT.
    if verdict is None:
        return _keyword_fallback(student_answer)

    return verdict


def looks_like_answer(text: str) -> bool:
    """Heuristic: does the user message look like an attempted answer?"""
    if not text:
        return False
    # Any non-empty reply (after stripping punctuation/whitespace) can be an
    # answer. Requiring >= 5 chars caused short but valid answers (e.g. "对",
    # "42", "yes") to be misclassified as non-answers and skip assessment.
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", text)
    return len(cleaned) >= 1
