"""Course, video, and knowledge graph endpoints."""

import json
import logging
import os
import re
import shutil
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db.neo4j import delete_node, get_graph
from app.db.postgres import AsyncSessionLocal
from app.limiter import limiter
from app.models.db import Course, CourseMaterial, KnowledgeEdge, KnowledgeNode, User, Video
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
from app.services.kg_extractor import extract_knowledge_graph
from app.services.video_service import process_video
from app.tasks.jobs import process_video_task

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_VIDEO_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MAX_MATERIAL_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
}
ALLOWED_MATERIAL_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MATERIAL_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
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
        raise HTTPException(status_code=415, detail="视频文件过小，可能不是有效视频")

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
            detail="文件格式与声明不符，请上传正确的视频文件",
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


def _build_video_url(file_path: str) -> str:
    """Build a servable URL for a video file stored under the upload directory."""
    if not file_path:
        return ""
    upload_dir = settings.upload_dir.rstrip("/")
    abs_path = os.path.abspath(file_path)
    abs_upload = os.path.abspath(upload_dir)
    if abs_path.startswith(abs_upload):
        rel = os.path.relpath(abs_path, abs_upload)
        return f"/uploads/{rel.replace(os.sep, '/')}"
    # Fallback: file not yet moved to uploads (still processing).
    return ""


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


class MaterialUploadResponse(BaseModel):
    material_id: str
    title: str
    file_type: str
    status: str


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
async def list_courses(skip: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Course).order_by(Course.created_at.desc()).offset(skip).limit(limit)
        )
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
            raise HTTPException(status_code=404, detail="课程不存在")

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
                "video_url": _build_video_url(v.file_path),
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
            raise HTTPException(status_code=404, detail="课程不存在")
        if course.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="没有权限操作该课程")
        return course


def _safe_remove(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as exc:
        logger.warning("Could not remove temporary file %s: %s", path, exc)


def _validate_material_upload(file: UploadFile) -> tuple[str, str]:
    """Validate file type and size for course material (PDF/image) uploads."""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_MATERIAL_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型: {ext}。仅支持 PDF 与图片（PNG/JPG/WEBP）",
        )
    if file.content_type not in ALLOWED_MATERIAL_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的 MIME 类型: {file.content_type}",
        )
    file_type = "pdf" if ext == ".pdf" else "image"
    return ext, file_type


ALLOWED_SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".json"}
ALLOWED_SUBTITLE_MIME_TYPES = {
    "application/x-subrip",
    "text/plain",
    "text/vtt",
    "application/json",
}
MAX_SUBTITLE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


def _parse_srt(content: str) -> list[dict]:
    """Parse SRT subtitle content into cue list."""
    cues = []
    blocks = re.split(r"\n\s*\n", content.strip())
    time_pattern = re.compile(
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
        r"\s*-->\s*"
        r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
    )
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        match = time_pattern.search(lines[0]) if re.match(r"\d+", lines[0]) else None
        if not match and len(lines) >= 2:
            match = time_pattern.search(lines[1])
        if not match:
            continue
        text_lines = lines[2:] if re.match(r"\d+", lines[0]) else lines[2:]
        if not text_lines and len(lines) >= 3:
            text_lines = lines[2:]
        start = (
            int(match.group(1)) * 3600
            + int(match.group(2)) * 60
            + int(match.group(3))
            + int(match.group(4)) / 1000
        )
        end = (
            int(match.group(5)) * 3600
            + int(match.group(6)) * 60
            + int(match.group(7))
            + int(match.group(8)) / 1000
        )
        cues.append({"start": round(start, 2), "end": round(end, 2), "text": " ".join(text_lines)})
    return cues


def _parse_vtt(content: str) -> list[dict]:
    """Parse WebVTT subtitle content into cue list."""
    cues = []
    lines = content.splitlines()
    if not lines or not lines[0].startswith("WEBVTT"):
        return cues
    time_pattern = re.compile(
        r"(\d{1,2}:)?(\d{2}):(\d{2})\.(\d{3})"
        r"\s*-->\s*"
        r"(\d{1,2}:)?(\d{2}):(\d{2})\.(\d{3})"
    )
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        match = time_pattern.search(line)
        if match:
            text_lines = []
            i += 1
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            start_h = int(match.group(1).rstrip(":")) if match.group(1) else 0
            start_m = int(match.group(2))
            start_s = int(match.group(3))
            start_ms = int(match.group(4))
            end_h = int(match.group(5).rstrip(":")) if match.group(5) else 0
            end_m = int(match.group(6))
            end_s = int(match.group(7))
            end_ms = int(match.group(8))
            start = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000
            end = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000
            cues.append(
                {"start": round(start, 2), "end": round(end, 2), "text": " ".join(text_lines)}
            )
        else:
            i += 1
    return cues


def _parse_subtitle_file(file_path: str, ext: str) -> list[dict]:
    """Parse SRT/VTT/JSON subtitle files into normalized cues."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    if ext == ".json":
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return [
                {
                    "start": float(c.get("start", 0)),
                    "end": float(c.get("end", 0)),
                    "text": str(c.get("text", "")),
                }
                for c in parsed
            ]
        raise HTTPException(status_code=422, detail="JSON 字幕格式应为对象数组")
    if ext == ".vtt":
        return _parse_vtt(content)
    return _parse_srt(content)


def _extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)
    except Exception as exc:
        logger.warning("Could not extract PDF text from %s: %s", file_path, exc)
        return ""


def _persist_uploaded_file(temp_path: str, course_id: str, ext: str) -> str:
    """Move an uploaded file from temp path to the course upload directory."""
    upload_dir = os.path.join(settings.upload_dir.rstrip("/"), "materials", course_id)
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, f"{uuid4()}{ext}")
    # shutil.move handles cross-device moves (temp dir and upload dir may live
    # on different filesystems inside a container), where os.rename would
    # raise OSError: Invalid cross-device link.
    shutil.move(temp_path, dest)
    return dest


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
                raise HTTPException(status_code=400, detail="上传文件为空")
            _validate_video_magic(first_chunk, ext)
            total_size = len(first_chunk)
            f.write(first_chunk)

            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_VIDEO_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="视频文件过大")
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


@router.post("/api/courses/{course_id}/materials", response_model=MaterialUploadResponse)
@limiter.limit("10/minute")
async def upload_course_material(
    request: Request,
    course_id: str,
    file: UploadFile = File(...),  # noqa: B008
    title: str | None = Form(None),  # noqa: B008
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Upload a PDF or image material for a course and extract text if possible."""
    await _require_course_owner(course_id, current_user)

    ext, file_type = _validate_material_upload(file)
    safe_title = title or (file.filename or "untitled")
    temp_path = f"/tmp/{uuid4()}{ext}"
    material_id = str(uuid4())

    total_size = 0
    try:
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_MATERIAL_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="资料文件过大，请控制在 50MB 以内")
                f.write(chunk)
            if total_size == 0:
                raise HTTPException(status_code=400, detail="上传文件为空")
    except HTTPException:
        _safe_remove(temp_path)
        raise
    except Exception as exc:
        _safe_remove(temp_path)
        raise HTTPException(
            status_code=400, detail=f"无法读取上传文件: {exc}"
        ) from exc
    finally:
        await file.close()

    # Persist the file under the configured upload directory.
    try:
        dest_path = _persist_uploaded_file(temp_path, course_id, ext)
    except Exception as exc:
        _safe_remove(temp_path)
        raise HTTPException(
            status_code=500, detail=f"保存文件失败: {exc}"
        ) from exc

    # Extract text for PDFs; images keep extracted_text empty for now (VLM caption
    # can be added later as an enhancement).
    extracted_text = ""
    status = "completed"
    if file_type == "pdf":
        extracted_text = _extract_pdf_text(dest_path)
        if not extracted_text.strip():
            status = "completed_with_warning"

    material = CourseMaterial(
        id=material_id,
        course_id=course_id,
        title=safe_title,
        file_type=file_type,
        file_path=dest_path,
        extracted_text=extracted_text or None,
        status=status,
    )
    async with AsyncSessionLocal() as session:
        session.add(material)
        await session.commit()

    return MaterialUploadResponse(
        material_id=material_id,
        title=safe_title,
        file_type=file_type,
        status=status,
    )


@router.get("/api/courses/{course_id}/materials")
async def list_course_materials(
    course_id: str,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """List all PDF/image materials for a course (owner only)."""
    await _require_course_owner(course_id, current_user)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CourseMaterial)
            .where(CourseMaterial.course_id == course_id)
            .order_by(CourseMaterial.created_at.desc())
        )
        materials = result.scalars().all()

    return [
        {
            "id": m.id,
            "title": m.title,
            "file_type": m.file_type,
            "status": m.status,
            "extracted_text": m.extracted_text,
            "created_at": m.created_at.isoformat(),
        }
        for m in materials
    ]


@router.delete("/api/materials/{material_id}")
async def delete_course_material(
    material_id: str,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Delete a course material and its stored file."""
    file_path_to_remove: str | None = None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CourseMaterial).where(CourseMaterial.id == material_id)
        )
        material = result.scalar_one_or_none()
        if material is None:
            raise HTTPException(status_code=404, detail="资料不存在")

        await _require_course_owner(material.course_id, current_user)
        # Capture the path before deletion so we can remove the file only after
        # the DB transaction commits. Deleting the file first would leave an
        # orphan DB row if the commit fails (e.g. DB connection drop).
        file_path_to_remove = material.file_path
        await session.delete(material)
        await session.commit()

    # Filesystem cleanup happens after a successful commit so a commit failure
    # never leaves an orphaned DB record pointing at a deleted file.
    if file_path_to_remove:
        _safe_remove(file_path_to_remove)

    return {"ok": True}


@router.post("/api/videos/{video_id}/subtitles")
@limiter.limit("10/minute")
async def upload_video_subtitles(
    request: Request,
    video_id: str,
    file: UploadFile = File(...),  # noqa: B008
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Upload an SRT/VTT/JSON subtitle file for a video (course owner only)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video is None:
            raise HTTPException(status_code=404, detail="视频不存在")
        await _require_course_owner(video.course_id, current_user)

    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_SUBTITLE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型: {ext}。仅支持 SRT / VTT / JSON",
        )
    if file.content_type not in ALLOWED_SUBTITLE_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的 MIME 类型: {file.content_type}",
        )

    temp_path = f"/tmp/{uuid4()}{ext}"
    total_size = 0
    try:
        with open(temp_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_SUBTITLE_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="字幕文件过大，请控制在 2MB 以内")
                f.write(chunk)
            if total_size == 0:
                raise HTTPException(status_code=400, detail="上传文件为空")
    except HTTPException:
        _safe_remove(temp_path)
        raise
    except Exception as exc:
        _safe_remove(temp_path)
        raise HTTPException(status_code=400, detail=f"无法读取字幕文件: {exc}") from exc
    finally:
        await file.close()

    try:
        cues = _parse_subtitle_file(temp_path, ext)
    except HTTPException:
        _safe_remove(temp_path)
        raise
    except Exception as exc:
        _safe_remove(temp_path)
        raise HTTPException(status_code=422, detail=f"字幕解析失败: {exc}") from exc

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video is not None:
            video.transcript_json = cues
            await session.commit()

    _safe_remove(temp_path)
    return {"video_id": video_id, "cues": len(cues)}


@router.get("/api/videos/{video_id}/subtitles")
async def get_video_subtitles(video_id: str):
    """Return the subtitle cues for a video."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Video).where(Video.id == video_id))
        video = result.scalar_one_or_none()
        if video is None:
            raise HTTPException(status_code=404, detail="视频不存在")
        return {"video_id": video_id, "cues": video.transcript_json or []}


@router.post("/api/courses/{course_id}/build-graph")
@limiter.limit("3/minute")
async def build_graph(
    course_id: str,
    body: BuildGraphRequest,
    request: Request,
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
                raise HTTPException(status_code=404, detail="该课程暂无视频")
            video_id = first_video.id
        else:
            video_result = await session.execute(
                select(Video).where(Video.id == video_id, Video.course_id == course_id)
            )
            if video_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="课程中未找到该视频")

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
                "position_x": n.position_x,
                "position_y": n.position_y,
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
        position_x=node.position_x,
        position_y=node.position_y,
    )


@router.patch("/api/nodes/{node_id}", response_model=KnowledgeNodeResponse)
async def update_knowledge_node(
    node_id: str,
    body: KnowledgeNodeUpdate,
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Update a knowledge node's name, description, threshold or position."""
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
        if body.position_x is not None:
            node.position_x = body.position_x
        if body.position_y is not None:
            node.position_y = body.position_y

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
        position_x=node.position_x,
        position_y=node.position_y,
    )


class _NodePositionUpdate(BaseModel):
    node_id: str
    position_x: float
    position_y: float


@router.patch("/api/courses/{course_id}/graph-positions")
async def update_graph_positions(
    course_id: str,
    body: list[_NodePositionUpdate],
    current_user: User = Depends(get_current_active_user),  # noqa: B008
):
    """Bulk update node positions for the course graph layout.

    This endpoint is used by the graph editor after a teacher drags nodes
    to a desired layout.
    """
    await _require_course_owner(course_id, current_user)

    if not body:
        return {"updated": 0}

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(KnowledgeNode).where(
                KnowledgeNode.course_id == course_id,
                KnowledgeNode.id.in_([item.node_id for item in body]),
            )
        )
        nodes = {node.id: node for node in result.scalars().all()}

        updated = 0
        for item in body:
            node = nodes.get(item.node_id)
            if node is None:
                continue
            node.position_x = item.position_x
            node.position_y = item.position_y
            updated += 1

        await session.commit()

    return {"updated": updated}


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
        course_id = node.course_id

        await session.delete(node)
        await session.commit()

    # Postgres CASCADE removed edges and mastery; mirror the deletion in Neo4j
    # so the graph DB does not keep stale nodes/relationships. Done after the
    # SQL commit so a Neo4j failure does not roll back the successful delete.
    try:
        await delete_node(course_id, node_id)
    except Exception as exc:
        logger.warning("Could not delete Neo4j node %s: %s", node_id, exc)

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
