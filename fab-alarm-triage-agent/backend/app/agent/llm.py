"""LLM construction, isolated so the provider is a one-file change."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.config import get_settings

# Low but non-zero: deterministic enough to be reproducible across eval runs, while
# still letting the model recover from a bad first parse on retry.
TEMPERATURE = 0.1


@lru_cache
def get_llm(**overrides: Any) -> BaseChatModel:
    from langchain_groq import ChatGroq

    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Triage needs a model; set it in .env or the "
            "environment, or inject a stub model when building the graph."
        )
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=TEMPERATURE,
        **overrides,
    )
