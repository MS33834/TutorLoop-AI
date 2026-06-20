"""Knowledge graph extraction agent."""

import base64
import json
import logging
from pathlib import Path

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.neo4j import create_nodes_and_edges
from app.db.postgres import AsyncSessionLocal
from app.models.db import Course, KnowledgeNode, Video, VideoFrame
from app.services.embedding_service import encode_text

logger = logging.getLogger(__name__)


SAMPLE_FRAME_COUNT = 4

FALLBACK_GRAPH = {
    "nodes": [
        {
            "id": "n1",
            "name": "课程导入",
            "description": "本课程的基础概念与学习目标概述（骨架示例数据）。",
            "threshold": 0.8,
        },
        {
            "id": "n2",
            "name": "核心知识点 A",
            "description": "课程中的第一个核心知识点（骨架示例数据）。",
            "threshold": 0.8,
        },
        {
            "id": "n3",
            "name": "核心知识点 B",
            "description": "在知识点 A 之后学习的进阶内容（骨架示例数据）。",
            "threshold": 0.8,
        },
    ],
    "edges": [
        {"from": "n1", "to": "n2", "relation": "prerequisite"},
        {"from": "n2", "to": "n3", "relation": "prerequisite"},
    ],
}


async def _load_video_and_frames(
    course_id: str, video_id: str
) -> tuple[Course | None, Video | None, list[VideoFrame]]:
    async with AsyncSessionLocal() as session:
        course_result = await session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = course_result.scalar_one_or_none()

        video_result = await session.execute(
            select(Video).where(Video.id == video_id, Video.course_id == course_id)
        )
        video = video_result.scalar_one_or_none()

        frames = []
        if video:
            frame_result = await session.execute(
                select(VideoFrame)
                .where(VideoFrame.video_id == video_id)
                .order_by(VideoFrame.timestamp_seconds)
            )
            frames = list(frame_result.scalars().all())

    return course, video, frames


def _sample_frame_paths(frames: list[VideoFrame], count: int = SAMPLE_FRAME_COUNT) -> list[str]:
    if not frames:
        return []
    if len(frames) <= count:
        return [f.file_path for f in frames]
    step = len(frames) // count
    return [frames[i * step].file_path for i in range(count)]


def _image_to_base64(path: str) -> str:
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode("utf-8")


def _build_prompt(course: Course, frame_paths: list[str], transcript: str | None) -> str:
    lines = [
        "你是一位课程知识图谱构建专家。请根据课程信息、视频关键帧和字幕，抽取知识点节点和它们之间的先修关系。",
        "",
        f"课程标题：{course.title}",
        f"课程描述：{course.description or '无'}",
    ]
    if transcript:
        lines.append(f"视频字幕/转录：{transcript}")
    lines.append(f"提供了 {len(frame_paths)} 张关键帧图片（base64 编码）。")
    lines.extend([
        "",
        "请严格按以下 JSON 格式返回，不要包含任何其他解释：",
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "name": "节点名称",
                        "description": "节点描述",
                        "threshold": 0.8,
                    }
                ],
                "edges": [
                    {
                        "from": "n1",
                        "to": "n2",
                        "relation": "prerequisite",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    ])
    return "\n".join(lines)


def _build_messages(prompt: str, frame_paths: list[str]) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for path in frame_paths:
        try:
            b64 = _image_to_base64(path)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        except Exception as exc:
            logger.warning("Could not read frame %s: %s", path, exc)

    return [{"role": "user", "content": content}]


async def _call_vlm(messages: list[dict]) -> dict:
    base_url = settings.vlm_base_url.rstrip("/") or settings.local_base_url.rstrip("/")
    api_key = settings.vlm_api_key or "local"
    model = settings.vlm_model

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]

    # Try to extract JSON from markdown code block if needed
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


async def extract_knowledge_graph(
    course_id: str, video_id: str, transcript: str | None = None
) -> dict:
    """Extract a knowledge graph for a course video and store it in Postgres + Neo4j.

    Falls back to a hardcoded skeleton graph if the VLM call fails.
    """
    course, video, frames = await _load_video_and_frames(course_id, video_id)
    if not course:
        raise ValueError(f"Course {course_id} not found")
    if not video:
        raise ValueError(f"Video {video_id} not found in course {course_id}")

    frame_paths = _sample_frame_paths(frames)
    prompt = _build_prompt(course, frame_paths, transcript)
    messages = _build_messages(prompt, frame_paths)

    try:
        graph = await _call_vlm(messages)
        logger.info("Extracted knowledge graph with %d nodes", len(graph.get("nodes", [])))
    except Exception as exc:
        logger.warning("VLM extraction failed (%s); using fallback skeleton graph.", exc)
        graph = dict(FALLBACK_GRAPH)
        graph["_fallback"] = True

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # Persist to Postgres
    async with AsyncSessionLocal() as session:
        for node in nodes:
            node_id = node.get("id")
            name = node.get("name", "")
            description = node.get("description", "")
            threshold = node.get("threshold", 0.8)
            embedding = encode_text(f"{name} {description}".strip())

            db_node = KnowledgeNode(
                course_id=course_id,
                name=name,
                description=description,
                threshold=threshold,
                neo4j_id=node_id,
                embedding=embedding,
            )
            session.add(db_node)

        await session.commit()

    # Persist to Neo4j
    try:
        await create_nodes_and_edges(course_id, nodes, edges)
    except Exception as exc:
        logger.warning("Could not write graph to Neo4j: %s", exc)

    return {
        "course_id": course_id,
        "video_id": video_id,
        "nodes": nodes,
        "edges": edges,
    }
