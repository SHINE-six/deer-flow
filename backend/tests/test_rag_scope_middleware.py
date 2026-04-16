from __future__ import annotations

from deerflow.agents.middlewares.rag_scope_middleware import (
    RagScopeMiddleware,
    build_scoped_rag_role,
)
from langchain_core.messages import ToolMessage


class DummyRequest:
    def __init__(self, tool_name: str, args: dict):
        self.tool_call = {
            "id": "call-1",
            "name": tool_name,
            "args": args,
        }


def test_build_scoped_rag_role_is_deterministic():
    role_a = build_scoped_rag_role("user-1", "finance-agent")
    role_b = build_scoped_rag_role("user-1", "finance-agent")
    role_c = build_scoped_rag_role("user-2", "finance-agent")

    assert role_a == role_b
    assert role_a != role_c
    assert role_a.startswith("user:")


def test_rag_scope_middleware_rewrites_matching_role():
    middleware = RagScopeMiddleware(
        agent_name="finance-agent",
        user_id="user-1",
    )
    request = DummyRequest(
        "rag_knowledge_base_rag_query",
        {"role": "finance-agent", "query": "latest budget"},
    )

    seen_roles: list[str] = []

    def handler(req):
        seen_roles.append(req.tool_call["args"]["role"])
        return "ok"

    result = middleware.wrap_tool_call(request, handler)

    assert result == "ok"
    assert seen_roles == [build_scoped_rag_role("user-1", "finance-agent")]


def test_rag_scope_middleware_leaves_other_tools_untouched():
    middleware = RagScopeMiddleware(
        agent_name="finance-agent",
        user_id="user-1",
    )
    request = DummyRequest(
        "bash",
        {"command": "pwd"},
    )

    def handler(req):
        return req.tool_call["args"]

    assert middleware.wrap_tool_call(request, handler) == {"command": "pwd"}


def test_rag_scope_middleware_requires_user_id_for_custom_agent_rag():
    middleware = RagScopeMiddleware(
        agent_name="finance-agent",
        user_id=None,
    )
    request = DummyRequest(
        "rag_knowledge_base_rag_query",
        {"role": "finance-agent", "query": "latest budget"},
    )

    result = middleware.wrap_tool_call(request, lambda req: "ok")

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "authenticated user identity is required" in str(result.content)
