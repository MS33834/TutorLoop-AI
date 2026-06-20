"""Course, video, and knowledge graph endpoints."""

import logging
import os
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.neo4j import get_graph
from app.db.postgres import AsyncSessionLocal
from app.models.db import Course, Video
from app.services.kg_agent import extract_knowledge_graph
from app.services.video_service import process_video

logger = logging.getLogger(__name__)

router = APIRouter()


class CourseCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: Optional[str] = None
    video_url: Optional[str] = None


class CourseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    created_at: str


class VideoUploadResponse(BaseModel):
    video_id: str
    title: str
    frame_count: int


class BuildGraphRequest(BaseModel):
    video_id: Optional[str] = None
    transcript: Optional[str] = None


@router.post("/api/courses", response_model=CourseResponse)
async def create_course(body: CourseCreate):
    course = Course(
        id=str(uuid4()),
        title=body.title,
        description=body.description,
        video_url=body.video_url,
    )
    async with AsyncSessionLocal() as session:
        session.add(course)
        await session.commit()
        await session.refresh(course)

    return CourseResponse(
        id=course.id,
        title=course.title,
        description=course.description,
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
        "created_at": course.created_at.isoformat(),
        "videos": [
            {
                "id": v.id,
                "title": v.title,
                "file_path": v.file_path,
                "video_url": f"/{v.file_path}",
                "duration_seconds": v.duration_seconds,
            }
            for v in videos
        ],
    }


@router.post("/api/courses/{course_id}/videos", response_model=VideoUploadResponse)
async def upload_video(
    course_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
):
    async with AsyncSessionLocal() as session:
        course_result = await session.execute(
            select(Course).where(Course.id == course_id)
        )
        if course_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Course not found")

    safe_title = title or (file.filename or "untitled")
    ext = os.path.splitext(file.filename or "")[1] or ".mp4"
    temp_path = f"/tmp/{uuid4()}{ext}"

    try:
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        video_id, frames = await process_video(course_id, safe_title, temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return VideoUploadResponse(
        video_id=video_id,
        title=safe_title,
        frame_count=len(frames),
    )


@router.post("/api/courses/{course_id}/build-graph")
async def build_graph(course_id: str, body: BuildGraphRequest):
    async with AsyncSessionLocal() as session:
        course_result = await session.execute(
            select(Course).where(Course.id == course_id)
        )
        if course_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Course not found")

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
    try:
        graph = await get_graph(course_id)
    except Exception as exc:
        logger.warning("Could not retrieve graph from Neo4j: %s", exc)
        graph = {"nodes": [], "edges": []}

    return graph
