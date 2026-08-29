"""Response/request shapes, kept in lockstep with frontend/lib/types.ts.

Field names here are the JSON wire format the frontend already expects —
see Agent, ChatMessage, ChatSession, and ChatCompletionsRequest in that file.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.db.models import Agent, AgentStatus, ChatSession

ChatRole = Literal["system", "user", "assistant"]


class AgentOut(BaseModel):
    id: str
    user_id: str
    status: AgentStatus
    host_port: int | None = None
    hermes_image_tag: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, agent: Agent) -> "AgentOut":
        return cls(
            id=str(agent.id),
            user_id=str(agent.user_id),
            status=agent.status,
            host_port=agent.host_port,
            hermes_image_tag=agent.hermes_image_tag,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


class ChatMessageIn(BaseModel):
    role: ChatRole
    content: str


class ChatCompletionsRequestIn(BaseModel):
    messages: list[ChatMessageIn]
    session_id: str | None = None
    stream: bool | None = None
    model: str | None = None


class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: str | None = None


class ChatSessionOut(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, session: ChatSession) -> "ChatSessionOut":
        return cls(id=session.id, title=session.title, created_at=session.created_at, updated_at=session.updated_at)


class ChatSessionListOut(BaseModel):
    sessions: list[ChatSessionOut]


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut]
