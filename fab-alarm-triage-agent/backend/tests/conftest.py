"""Test fixtures.

Database-backed tests run against a dedicated `<db>_test` database, seeded once per
session. They skip rather than fail when Postgres is unreachable, so `pytest` still
works on a machine with no stack running.
"""

from __future__ import annotations

import os

# Must be set before app.config is imported — Settings is cached.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ["POSTGRES_DB"] = os.environ.get("POSTGRES_DB", "fab_mes") + "_test"

import psycopg  # noqa: E402
import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402


def _admin_dsn(settings) -> str:
    return (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/postgres"
    )


@pytest.fixture(scope="session")
def database() -> None:
    """Create the test database, then seed it once."""
    settings = get_settings()
    try:
        with psycopg.connect(_admin_dsn(settings), autocommit=True, connect_timeout=3) as conn:
            exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (settings.postgres_db,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{settings.postgres_db}"')
    except psycopg.OperationalError as exc:  # pragma: no cover - environment dependent
        pytest.skip(
            f"Postgres unavailable at {settings.postgres_host}:{settings.postgres_port}: {exc}"
        )

    import asyncio

    from app.seed.seed import seed

    asyncio.run(seed(reset=True))


@pytest.fixture
async def session(database):
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def client(database):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
async def _close_agent_runtime():
    """Tear down the checkpointer between tests.

    Its connection pool starts background tasks bound to the running event loop, and
    pytest-asyncio gives each test a fresh loop — a pool held over from a previous test
    hangs rather than failing.
    """
    yield
    from app.agent import runtime

    await runtime.close_checkpointer()
    runtime.reset()
