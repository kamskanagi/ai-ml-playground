"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import mes, triage
from app.config import get_settings
from app.db.session import create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all()
    yield
    # The checkpointer holds a connection pool; close it so shutdown is clean.
    from app.agent.runtime import close_checkpointer

    await close_checkpointer()


app = FastAPI(
    title="Fab Alarm Triage MES",
    version="0.1.0",
    summary="Mock MES and alarm-triage agent for semiconductor fab equipment",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(mes.router)
app.include_router(triage.router)


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
async def ready() -> dict[str, str]:
    """Readiness probe — verifies the database is actually reachable."""
    from sqlalchemy import text

    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready", "model": get_settings().groq_model}
