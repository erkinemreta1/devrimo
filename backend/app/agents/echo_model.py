"""A model that answers without a provider, for tests and offline dev.

Selected by ``AGENT_RUNTIME=fake``. Everything else in the stack stays real —
the Agno ``Agent``, its database, session persistence, and the SSE
serialization are all exercised exactly as in production; only the network
call to OpenRouter is replaced. That is deliberate: the bugs worth catching in
this codebase live in session wiring and stream shaping, not in the provider.

It never calls a tool, so a test that needs tool-call events should assert on
:mod:`app.api.v1.chat`'s serializer directly rather than driving it from here.
"""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any

from agno.models.base import Model
from agno.models.response import ModelResponse

ECHO_PREFIX = "[echo] "


def _last_user_text(messages: Any) -> str:
    for message in reversed(list(messages or [])):
        role = getattr(message, "role", None) or (message.get("role") if isinstance(message, dict) else None)
        if role != "user":
            continue
        content = getattr(message, "content", None) or (message.get("content") if isinstance(message, dict) else None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):  # multimodal content blocks
            return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


@dataclass
class EchoModel(Model):
    id: str = "echo"
    name: str = "EchoModel"
    provider: str = "fake"

    def _reply(self, messages: Any) -> str:
        return f"{ECHO_PREFIX}{_last_user_text(messages)}".strip()

    def _messages_from(self, args: tuple, kwargs: dict) -> Any:
        return kwargs.get("messages") or (args[0] if args else None)

    def invoke(self, *args, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant", content=self._reply(self._messages_from(args, kwargs)))

    async def ainvoke(self, *args, **kwargs) -> ModelResponse:
        return self.invoke(*args, **kwargs)

    def invoke_stream(self, *args, **kwargs) -> Iterator[ModelResponse]:
        text = self._reply(self._messages_from(args, kwargs))
        # Word-at-a-time so tests see a genuinely chunked stream rather than
        # one delta that happens to contain the whole answer.
        for index, word in enumerate(text.split(" ")):
            yield ModelResponse(role="assistant", content=word if index == 0 else f" {word}")

    async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
        for chunk in self.invoke_stream(*args, **kwargs):
            yield chunk

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        if isinstance(response, ModelResponse):
            return response
        return ModelResponse(role="assistant", content=str(response))

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        if isinstance(response, ModelResponse):
            return response
        return ModelResponse(role="assistant", content=str(response))
