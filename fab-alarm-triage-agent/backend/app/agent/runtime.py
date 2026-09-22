"""Process-wide agent runtime: checkpointer, MCP tools, compiled graph.

All three are expensive to build and safe to share, so they are created once during
application startup and reused. Holding them here rather than on the FastAPI app keeps
the eval harness and scripts able to use the same graph without a web server.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.config import get_settings

_pool: Any = None
_checkpointer: Any = None
_tools: list[BaseTool] | None = None
_graph: Any = None


async def open_checkpointer() -> Any:
    """Create the Postgres checkpointer and its tables.

    A connection pool rather than a single connection: paused runs resume on whichever
    worker receives the review, so this is touched concurrently. The checkpointer
    requires autocommit and dict rows.
    """
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    _pool = AsyncConnectionPool(
        conninfo=get_settings().sync_dsn,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    global _pool, _checkpointer, _graph
    if _pool is not None:
        await _pool.close()
    _pool = _checkpointer = _graph = None


async def load_mcp_tools() -> list[BaseTool]:
    """Connect to the MCP server and load its tools."""
    global _tools
    if _tools is not None:
        return _tools

    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(
        {"fab-mes": {"transport": "streamable_http", "url": get_settings().mcp_url}}
    )
    _tools = await client.get_tools()
    return _tools


async def get_graph() -> Any:
    """The compiled triage graph, built once."""
    global _graph
    if _graph is not None:
        return _graph

    from app.agent.graph import build_graph
    from app.agent.llm import get_llm
    from app.db.session import get_sessionmaker
    from app.services.triage import on_decision, on_propose

    _graph = build_graph(
        tools=await load_mcp_tools(),
        llm=get_llm(),
        sessionmaker=get_sessionmaker(),
        checkpointer=await open_checkpointer(),
        on_propose=on_propose,
        on_decision=on_decision,
    )
    return _graph


def reset() -> None:
    """Drop cached state. Used by tests."""
    global _tools, _graph
    _tools = _graph = None
