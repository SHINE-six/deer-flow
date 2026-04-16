"""Scope RAG tool calls to the authenticated user and current custom agent."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

RAG_TOOL_PREFIX = "rag_knowledge_base_"


def build_scoped_rag_role(user_id: str, agent_name: str) -> str:
    """Build a deterministic scoped RAG role id for a user/agent pair."""
    user_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
    return f"user:{user_hash}:{agent_name.lower()}"


class RagScopeMiddleware(AgentMiddleware[AgentState]):
    """Rewrite RAG role args to user-scoped role ids for custom agents."""

    def __init__(self, *, agent_name: str | None, user_id: str | None):
        self._agent_name = agent_name.lower() if agent_name else None
        self._user_id = user_id

    def _should_scope(self, request: ToolCallRequest) -> bool:
        tool_name = str(request.tool_call.get("name") or "")
        if not tool_name.startswith(RAG_TOOL_PREFIX):
            return False
        if not self._agent_name:
            return False
        args = request.tool_call.get("args")
        if not isinstance(args, dict):
            return False
        return args.get("role") == self._agent_name

    def _build_missing_user_message(self, request: ToolCallRequest) -> ToolMessage:
        tool_name = str(request.tool_call.get("name") or "unknown_tool")
        tool_call_id = str(request.tool_call.get("id") or "missing_tool_call_id")
        return ToolMessage(
            content=(
                "Error: authenticated user identity is required for custom-agent "
                "RAG access."
            ),
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

    def _scope_request(self, request: ToolCallRequest) -> ToolCallRequest:
        if self._user_id is None:
            raise RuntimeError("missing authenticated user id")

        args = request.tool_call.get("args")
        assert isinstance(args, dict)
        request.tool_call["args"] = {
            **args,
            "role": build_scoped_rag_role(self._user_id, self._agent_name or ""),
        }
        return request

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if self._should_scope(request):
            if self._user_id is None:
                return self._build_missing_user_message(request)
            request = self._scope_request(request)
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if self._should_scope(request):
            if self._user_id is None:
                return self._build_missing_user_message(request)
            request = self._scope_request(request)
        return await handler(request)
