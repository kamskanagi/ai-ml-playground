"""A scripted chat model.

Lets the graph be driven through every path — tool loops, parse failures, the interrupt
and the resume — without a single API call, so the agent tests are fast, deterministic
and free.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class StubChatModel(BaseChatModel):
    """Replays `script` for ordinary calls and `structured_script` for structured ones.

    An entry in `structured_script` that is an Exception is raised instead of returned,
    which is how the structured-output retry and fallback paths get exercised.
    """

    script: list[BaseMessage] = Field(default_factory=list)
    structured_script: list[Any] = Field(default_factory=list)
    prompts_seen: list[list[BaseMessage]] = Field(default_factory=list)
    structured_calls: int = 0
    bound_tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.prompts_seen.append(list(messages))
        message = self.script.pop(0) if self.script else AIMessage(content="no more script")
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> StubChatModel:
        self.bound_tools = list(tools)
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        model = self

        class _Structured:
            async def ainvoke(self, messages: Any, **kw: Any) -> Any:
                model.structured_calls += 1
                if not model.structured_script:
                    raise ValueError("structured_script exhausted")
                item = model.structured_script.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item

            def invoke(self, messages: Any, **kw: Any) -> Any:
                raise NotImplementedError("tests drive the graph asynchronously")

        return _Structured()
