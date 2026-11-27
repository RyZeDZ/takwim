"""Backend entry point. Run with:  uvicorn app.main:app --reload   then open http://localhost:8000/docs"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_admin
from .config import settings
from .db import SessionLocal, init_db
from .routes import admin_data, auth, imports


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_admin(db)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Smart timetables for the department: import, generate, absences, extra sessions.",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth.router, admin_data.router, imports.router):
    app.include_router(r)


@app.get("/health", tags=["health"])
def health():
    return {"ok": True}
