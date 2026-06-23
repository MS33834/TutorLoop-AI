"""Course, video, and knowledge graph endpoints."""

import logging
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.neo4j import get_graph
from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import Course, KnowledgeEdge, KnowledgeNode, User, Video
from app.schemas import (
    KnowledgeEdgeCreate,
    KnowledgeEdgeResponse,
    KnowledgeNodeCreate,
    KnowledgeNodeResponse,
    KnowledgeNodeUpdate,
    UserResponse,
)
from app.services.auth_service import get_current_active_user
from app.services.class_report_service import generate_class_report
from app.services.embedding_service import encode_text
from app.services.kg_agent import extract_knowledge_graph
from app.services.video_service import process_video
from app.tasks.jobs import process_video_task

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}


def _validate_video_upload(file: UploadFile) -> str:
    """Validate file type and size for video uploads."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
        )
    if file.content_type not in ALLOWED_VIDEO_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported MIME type: {file.content_type}. Allowed video uploads only",
        )
    return ext


def _validate_video_magic(first_bytes: bytes, ext: str) -> None:
    """Validate that the first bytes of the file look like the declared video format."""
    if len(first_bytes) < 12:
        raise HTTPException(status_code=415, detail="File too small to be a valid video")

    if ext in {".mp4", ".mov"}:
        valid = first_bytes[4:8] in {b"ftyp", b"moov", b"mdat"}
    elif ext == ".avi":
        valid = first_bytes[:4] == b"RIFF" and first_bytes[8:12] == b"AVI "
    elif ext in {".mkv", ".webm"}:
        valid = first_bytes[:4] == b"\x1a\x45\xdf\xa3"
    else:
        valid = True

    if not valid:
        raise HTTPException(
            status_code=415,
            detail="File signature does not match declared video format",
        )


def _serialize_user(user: User | None) -> UserResponse | None:
    if not user:
        return None
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    video_url: str | None = None


class CourseResponse(BaseModel):
    id: str
    title: str
    description: str | None
    created_by: str | None
    created_at: str


class VideoUploadResponse(BaseModel):
    video_id: str
    title: str
    status: str
    frame_count: int | None = None


class BuildGraphRequest(BaseModel):
    video_id: str | None = None
    transcript: str | None = None


@router.post("/api/courses", response_model=CourseResponse)
async def create_course(
    body: CourseCreate,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    course = Course(
        id=str(uuid4()),
        title=body.title,
        description=body.description,
        video_url=body.video_url,
        created_by=current_user.id,
    )
    async with AsyncSessionLocal() as session:
        session.add(course)
        await session.commit()
        await session.refresh(course)

    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
        created_by=course.created_by,
        created_at=course.created_at.isoformat(),
    )


@router.get("/api/courses")
async def list_courses():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Course).order_by(Course.created_at.desc()))
        courses = result.scalars().all()

    return [
        {
            "id": c.id,
            "title": c.title,
            "description": c.description,
            "created_by": c.created_by,
            "created_at": c.created_at.isoformat(),
        }
        for c in courses
    ]


@router.get("/api/courses/{course_id}")
async def get_course(course_id: str):
    async with AsyncSessionLocal() as session:
        course_result = await session.execute(select(Course).where(Course.id == course_id))
        course = course_result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")

        video_result = await session.execute(
            select(Video).where(Video.course_id == course_id).order_by(Video.created_at)
        )
        videos = video_result.scalars().all()

    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "created_by": course.created_by,
        "created_at": course.created_at.isoformat(),
        "videos": [
            {
                "id": v.id,
                "title": v.title,
                "video_url": f"/{v.file_path}",
                "duration_seconds": v.duration_seconds,
                "status": v.status,
            }
            for v in videos
        ],
    }


async def _require_course_owner(course_id: str, current_user: User) -> Course:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Course).where(Course.id == course_id))
        course = result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
        if course.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该课程")
        return course


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as exc:
        logger.warning("Could not remove temporary file %s: %s", path, exc)


@router.post("/api/courses/{course_id}/videos", response_model=VideoUploadResponse)
@limiter.limit("10/minute")
async def upload_video(
    request: Request,
    course_id: str,
    file: UploadFile = File(...),  # noqa: B008
    title: str | None = Form(None),  # noqa: B008
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    await _require_course_owner(course_id, current_user)

    ext = _validate_video_upload(file)
    safe_title = title or (file.filename or "untitled")
    temp_path = f"/tmp/{uuid4()}{ext}"
    video_id = str(uuid4())

    # Save uploaded bytes to a stable temp path that the worker can read.
    total_size = 0
    try:
        with open(temp_path, "wb") as f:
            first_chunk = await file.read(8192)
            if not first_chunk:
                raise HTTPException(status_code=400, detail="Empty upload file")
            _validate_video_magic(first_chunk, ext)
            total_size = len(first_chunk)
            f.write(first_chunk)

            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_VIDEO_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="Video file too large")
                f.write(chunk)
    except HTTPException:
        _safe_remove(temp_path)
        raise
    except Exception as exc:
        _safe_remove(temp_path)
        raise HTTPException(
            status_code=400, detail=f"Could not read uploaded file: {exc}"
        ) from exc
    finally:
        await file.close()

    # Create a placeholder video record in "processing" state.
    video = Video(
        id=video_id,
        course_id=course_id,
        title=safe_title,
        file_path=temp_path,
        status="processing",
    )
    async with AsyncSessionLocal() as session:
        session.add(video)
        await session.commit()

    # Enqueue background processing if Redis is connected, otherwise process inline.
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        await redis.enqueue_job(
            process_video_task.__name__,
            video_id,
            course_id,
            safe_title,
            temp_path,
        )
        return VideoUploadResponse(
            video_id=video_id,
            title=safe_title,
            status="processing",
        )

    # Synchronous fallback when no task queue is configured.
    try:
        _, frames = await process_video(course_id, safe_title, temp_path, video_id=video_id)
        return VideoUploadResponse(
            video_id=video_id,
            title=safe_title,
            status="completed",
            frame_count=len(frames),
        )
    finally:
        _safe_remove(temp_path)


@router.post("/api/courses/{course_id}/build-graph")
async def build_graph(
    course_id: str,
    body: BuildGraphRequest,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    await _require_course_owner(course_id, current_user)

    async with AsyncSessionLocal() as session:
        video_id = body.video_id
        if not video_id:
            video_result = await session.execute(
                select(Video).where(Video.course_id == course_id)
            )
            first_video = video_result.scalar_one_or_none()
            if first_video is None:
                raise HTTPException(status_code=404, detail="No video in course")
            video_id = first_video.id
        else:
            video_result = await session.execute(
                select(Video).where(Video.id == video_id, Video.course_id == course_id)
            )
            if video_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="Video not found in course")

    graph = await extract_knowledge_graph(course_id, video_id, body.transcript)
    return graph


@router.get("/api/courses/{course_id}/graph")
async def get_course_graph(course_id: str):
    """Return the course knowledge graph from Postgres, falling back to Neo4j."""
    async with AsyncSessionLocal() as session:
        nodes_result = await session.execute(
            select(KnowledgeNode)
            .where(KnowledgeNode.course_id == course_id)
            .order_by(KnowledgeNode.created_at)
        )
        nodes = list(nodes_result.scalars().all())

        if not nodes:
            try:
                return await get_graph(course_id)
            except Exception as exc:
                logger.warning("Could not retrieve graph from Neo4j: %s", exc)
                return {"nodes": [], "edges": []}

        edges_result = await session.execute(
            select(KnowledgeEdge).where(KnowledgeEdge.course_id == course_id)
        )
        edges = list(edges_result.scalars().all())

    return {
        "nodes": [
            {
                "id": n.id,
                "name": n.name,
                "description": n.description or "",
                "threshold": n.threshold,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "from": e.source_id,
                "to": e.target_id,
                "relation": e.relation,
            }
            for e in edges
        ],
    }


@router.get("/api/courses/{course_id}/class-report")
@limiter.limit("30/minute")
async def get_class_report_endpoint(
    request: Request,
    course_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Return aggregated class-level analytics for the course owner."""
    await _require_course_owner(course_id, current_user)
    return await generate_class_report(course_id, skip=skip, limit=limit)


@router.post("/api/courses/{course_id}/nodes", response_model=KnowledgeNodeResponse)
async def create_knowledge_node(
    course_id: str,
    body: KnowledgeNodeCreate,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Create a new knowledge node for the course."""
    await _require_course_owner(course_id, current_user)

    async with AsyncSessionLocal() as session:
        embedding = encode_text(f"{body.name} {body.description or ''}".strip())
        node = KnowledgeNode(
            id=str(uuid4()),
            course_id=course_id,
            name=body.name,
            description=body.description,
            threshold=body.threshold,
            embedding=embedding,
        )
        session.add(node)
        await session.commit()
        await session.refresh(node)

    return KnowledgeNodeResponse(
        id=node.id,
        course_id=node.course_id,
        name=node.name,
        description=node.description,
        threshold=node.threshold,
    )


@router.patch("/api/nodes/{node_id}", response_model=KnowledgeNodeResponse)
async def update_knowledge_node(
    node_id: str,
    body: KnowledgeNodeUpdate,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Update a knowledge node's name, description or threshold."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(KnowledgeNode).where(KnowledgeNode.id == node_id))
        node = result.scalar_one_or_none()
        if node is None:
            raise HTTPException(status_code=404, detail="知识点不存在")

        await _require_course_owner(node.course_id, current_user)

        text_changed = False
        if body.name is not None:
            node.name = body.name
            text_changed = True
        if body.description is not None:
            node.description = body.description
            text_changed = True
        if body.threshold is not None:
            node.threshold = body.threshold

        if text_changed:
            node.embedding = encode_text(f"{node.name} {node.description or ''}".strip())

        await session.commit()
        await session.refresh(node)

    return KnowledgeNodeResponse(
        id=node.id,
        course_id=node.course_id,
        name=node.name,
        description=node.description,
        threshold=node.threshold,
    )


@router.delete("/api/nodes/{node_id}")
async def delete_knowledge_node(
    node_id: str,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Delete a knowledge node and its associated edges / mastery records."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(KnowledgeNode).where(KnowledgeNode.id == node_id))
        node = result.scalar_one_or_none()
        if node is None:
            raise HTTPException(status_code=404, detail="知识点不存在")

        await _require_course_owner(node.course_id, current_user)

        await session.delete(node)
        await session.commit()

    return {"ok": True}


@router.post("/api/courses/{course_id}/edges", response_model=KnowledgeEdgeResponse)
async def create_knowledge_edge(
    course_id: str,
    body: KnowledgeEdgeCreate,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Create a dependency edge between two knowledge nodes."""
    await _require_course_owner(course_id, current_user)

    if body.source_id == body.target_id:
        raise HTTPException(status_code=400, detail="边的起点和终点不能相同")

    async with AsyncSessionLocal() as session:
        # Verify both nodes belong to the course.
        node_result = await session.execute(
            select(KnowledgeNode.id).where(
                KnowledgeNode.course_id == course_id,
                KnowledgeNode.id.in_([body.source_id, body.target_id]),
            )
        )
        found_node_ids = {row[0] for row in node_result.all()}
        if len(found_node_ids) != 2:
            raise HTTPException(status_code=400, detail="起点或终点不属于该课程")

        edge = KnowledgeEdge(
            id=str(uuid4()),
            course_id=course_id,
            source_id=body.source_id,
            target_id=body.target_id,
            relation=body.relation or "prerequisite",
        )
        session.add(edge)
        try:
            await session.commit()
            await session.refresh(edge)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="该边已存在") from exc

    return KnowledgeEdgeResponse(
        id=edge.id,
        course_id=edge.course_id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        relation=edge.relation,
    )


@router.delete("/api/edges/{edge_id}")
async def delete_knowledge_edge(
    edge_id: str,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Delete a dependency edge."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(KnowledgeEdge).where(KnowledgeEdge.id == edge_id))
        edge = result.scalar_one_or_none()
        if edge is None:
            raise HTTPException(status_code=404, detail="边不存在")

        await _require_course_owner(edge.course_id, current_user)

        await session.delete(edge)
        await session.commit()

    return {"ok": True}
