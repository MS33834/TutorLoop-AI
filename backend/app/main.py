"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.neo4j import close_driver
from app.db.postgres import close_db, init_db
from app.routers import chat, courses, users

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    await init_db()
    yield
    await close_db()
    await close_driver()


app = FastAPI(
    title="TutorLoop-AI Gateway",
    version="0.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(courses.router)
app.include_router(users.router)
app.mount(
    "/uploads",
    StaticFiles(directory=settings.upload_dir, check_dir=False),
    name="uploads",
)
