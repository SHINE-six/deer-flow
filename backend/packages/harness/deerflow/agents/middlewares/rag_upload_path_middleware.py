"""Rewrite virtual file paths in RAG tool calls to rag-orchestrator-visible paths."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.agents.middlewares.rag_scope_middleware import RAG_TOOL_PREFIX
from deerflow.config.paths import VIRTUAL_PATH_PREFIX

_DEFAULT_RAG_DATA_MOUNT = "/app/deer-flow-data"


def _get_thread_id() -> str | None:
    """Extract thread_id from the current LangGraph runnable context."""
    try:
        from langgraph.config import get_config

        return get_config().get("configurable", {}).get("thread_id")
    except RuntimeError:
        return None


class RagUploadPathMiddleware(AgentMiddleware[AgentState]):
    """Translate sandbox virtual paths to rag-orchestrator-visible paths.

    When the agent calls ``rag_knowledge_base_*`` tools with a ``file_path``
    argument that uses the sandbox virtual prefix (``/mnt/user-data/…``), this
    middleware rewrites it to a path that rag-orchestrator can open via its
    read-only volume mount of DeerFlow thread data.
    """

    def __init__(self) -> None:
        self._rag_data_mount = os.environ.get(
            "RAG_ORCHESTRATOR_DATA_MOUNT", _DEFAULT_RAG_DATA_MOUNT
        ).rstrip("/")

    # ── helpers ──────────────────────────────────────────────────────────

    def _should_rewrite(self, request: ToolCallRequest) -> bool:
        tool_name = str(request.tool_call.get("name") or "")
        if not tool_name.startswith(RAG_TOOL_PREFIX):
            return False
        args = request.tool_call.get("args")
        if not isinstance(args, dict):
            return False
        file_path = args.get("file_path")
        if not isinstance(file_path, str):
            return False
        return file_path == VIRTUAL_PATH_PREFIX or file_path.startswith(VIRTUAL_PATH_PREFIX + "/")

    def _rewrite_path(self, thread_id: str, virtual_path: str) -> str:
        """Translate a sandbox virtual path to a rag-orchestrator-visible path.

        Raises:
            ValueError: On invalid prefix or path-traversal attempt.
        """
        stripped = virtual_path.lstrip("/")
        prefix = VIRTUAL_PATH_PREFIX.lstrip("/")

        if stripped != prefix and not stripped.startswith(prefix + "/"):
            raise ValueError(f"Path must start with {VIRTUAL_PATH_PREFIX}")

        relative = stripped[len(prefix):].lstrip("/")

        # Reject path-traversal attempts.
        if ".." in relative.split("/"):
            raise ValueError("Access denied: path traversal detected")

        return f"{self._rag_data_mount}/threads/{thread_id}/user-data/{relative}"

    def _rewrite_request(self, request: ToolCallRequest, thread_id: str) -> ToolCallRequest:
        args = request.tool_call.get("args")
        assert isinstance(args, dict)
        new_path = self._rewrite_path(thread_id, args["file_path"])
        request.tool_call["args"] = {**args, "file_path": new_path}
        return request

    def _build_error(self, request: ToolCallRequest, detail: str) -> ToolMessage:
        tool_name = str(request.tool_call.get("name") or "unknown_tool")
        tool_call_id = str(request.tool_call.get("id") or "missing_tool_call_id")
        return ToolMessage(
            content=f"Error: {detail}",
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

    # ── tool-call interception ──────────────────────────────────────────

    def _handle(self, request: ToolCallRequest) -> ToolCallRequest | ToolMessage:
        """Shared logic for sync/async wrappers.

        Returns the (possibly rewritten) request on success, or a
        ``ToolMessage`` error.
        """
        if not self._should_rewrite(request):
            return request

        thread_id = _get_thread_id()
        if not thread_id:
            return self._build_error(
                request,
                "thread_id is required to resolve uploaded file paths for RAG tools.",
            )

        try:
            return self._rewrite_request(request, thread_id)
        except ValueError as exc:
            return self._build_error(request, str(exc))

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        result = self._handle(request)
        if isinstance(result, ToolMessage):
            return result
        return handler(result)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        result = self._handle(request)
        if isinstance(result, ToolMessage):
            return result
        return await handler(result)
