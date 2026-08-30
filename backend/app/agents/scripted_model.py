"""Deterministic model double that can exercise Agno tool and HITL paths."""

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

from agno.models.base import Model
from agno.models.response import ModelResponse


@dataclass
class ScriptedModel(Model):
    """Returns a fixed sequence of model responses, then repeats the last one."""

    responses: list[ModelResponse] = field(default_factory=list)
    id: str = "scripted"
    name: str = "ScriptedModel"
    provider: str = "fake"
    _position: int = 0

    def _next(self) -> ModelResponse:
        if not self.responses:
            return ModelResponse(role="assistant", content="[scripted]")
        index = min(self._position, len(self.responses) - 1)
        self._position += 1
        return self.responses[index]

    def invoke(self, *args, **kwargs) -> ModelResponse:
        return self._next()

    async def ainvoke(self, *args, **kwargs) -> ModelResponse:
        return self._next()

    def invoke_stream(self, *args, **kwargs) -> Iterator[ModelResponse]:
        yield self._next()

    async def ainvoke_stream(self, *args, **kwargs) -> AsyncIterator[ModelResponse]:
        yield self._next()

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        if isinstance(response, ModelResponse):
            return response
        return ModelResponse(role="assistant", content=str(response))

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return self._parse_provider_response(response)
