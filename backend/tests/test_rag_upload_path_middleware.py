from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage

from deerflow.agents.middlewares.rag_upload_path_middleware import (
    RagUploadPathMiddleware,
    _get_thread_id,
)


THREAD_ID = "thread-abc123"


class DummyRequest:
    def __init__(self, tool_name: str, args: dict):
        self.tool_call = {
            "id": "call-1",
            "name": tool_name,
            "args": args,
        }


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def middleware(monkeypatch):
    monkeypatch.delenv("RAG_ORCHESTRATOR_DATA_MOUNT", raising=False)
    return RagUploadPathMiddleware()


@pytest.fixture()
def _patch_thread_id(monkeypatch):
    """Make _get_thread_id return THREAD_ID."""
    monkeypatch.setattr(
        "deerflow.agents.middlewares.rag_upload_path_middleware._get_thread_id",
        lambda: THREAD_ID,
    )


@pytest.fixture()
def _patch_no_thread_id(monkeypatch):
    """Make _get_thread_id return None."""
    monkeypatch.setattr(
        "deerflow.agents.middlewares.rag_upload_path_middleware._get_thread_id",
        lambda: None,
    )


# ── valid rewrite ────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_patch_thread_id")
def test_rewrites_virtual_upload_path(middleware):
    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/report.pdf"},
    )
    seen_paths: list[str] = []

    def handler(req):
        seen_paths.append(req.tool_call["args"]["file_path"])
        return "ok"

    result = middleware.wrap_tool_call(request, handler)

    assert result == "ok"
    assert seen_paths == [
        f"/app/deer-flow-data/threads/{THREAD_ID}/user-data/uploads/report.pdf"
    ]


@pytest.mark.usefixtures("_patch_thread_id")
def test_rewrites_diff_document(middleware):
    request = DummyRequest(
        "rag_knowledge_base_diff_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/v2.pdf", "doc_id": "my-doc"},
    )

    def handler(req):
        return req.tool_call["args"]

    result = middleware.wrap_tool_call(request, handler)

    assert result["file_path"] == f"/app/deer-flow-data/threads/{THREAD_ID}/user-data/uploads/v2.pdf"
    assert result["doc_id"] == "my-doc"
    assert result["role"] == "default"


@pytest.mark.usefixtures("_patch_thread_id")
def test_rewrites_confirm_full_ingest(middleware):
    request = DummyRequest(
        "rag_knowledge_base_confirm_full_ingest",
        {"role": "default", "file_path": "/mnt/user-data/uploads/doc.pdf", "doc_id": "doc-1"},
    )

    def handler(req):
        return req.tool_call["args"]["file_path"]

    result = middleware.wrap_tool_call(request, handler)
    assert result == f"/app/deer-flow-data/threads/{THREAD_ID}/user-data/uploads/doc.pdf"


@pytest.mark.usefixtures("_patch_thread_id")
def test_rewrites_confirm_section_updates(middleware):
    request = DummyRequest(
        "rag_knowledge_base_confirm_section_updates",
        {
            "role": "default",
            "file_path": "/mnt/user-data/uploads/doc.pdf",
            "doc_id": "doc-1",
            "section_ids": ["s1", "s2"],
        },
    )

    def handler(req):
        return req.tool_call["args"]

    result = middleware.wrap_tool_call(request, handler)
    assert result["file_path"] == f"/app/deer-flow-data/threads/{THREAD_ID}/user-data/uploads/doc.pdf"
    assert result["section_ids"] == ["s1", "s2"]


# ── non-matching cases ───────────────────────────────────────────────────


def test_non_rag_tool_unchanged(middleware):
    request = DummyRequest("bash", {"command": "pwd"})

    def handler(req):
        return req.tool_call["args"]

    assert middleware.wrap_tool_call(request, handler) == {"command": "pwd"}


def test_rag_tool_without_file_path_unchanged(middleware):
    request = DummyRequest(
        "rag_knowledge_base_rag_query",
        {"role": "default", "query": "latest budget"},
    )

    def handler(req):
        return req.tool_call["args"]

    result = middleware.wrap_tool_call(request, handler)
    assert result == {"role": "default", "query": "latest budget"}


@pytest.mark.usefixtures("_patch_thread_id")
def test_already_real_path_unchanged(middleware):
    """Paths that don't start with /mnt/user-data should pass through."""
    real_path = "/app/deer-flow-data/threads/t1/user-data/uploads/file.pdf"
    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": real_path},
    )

    def handler(req):
        return req.tool_call["args"]["file_path"]

    result = middleware.wrap_tool_call(request, handler)
    assert result == real_path


# ── error cases ──────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_patch_no_thread_id")
def test_missing_thread_id_returns_error(middleware):
    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/report.pdf"},
    )

    result = middleware.wrap_tool_call(request, lambda req: "ok")

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "thread_id is required" in str(result.content)


@pytest.mark.usefixtures("_patch_thread_id")
def test_path_traversal_returns_error(middleware):
    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/../../etc/passwd"},
    )

    result = middleware.wrap_tool_call(request, lambda req: "ok")

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "path traversal" in str(result.content)


# ── other args preserved ─────────────────────────────────────────────────


@pytest.mark.usefixtures("_patch_thread_id")
def test_preserves_other_args(middleware):
    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {
            "role": "finance",
            "file_path": "/mnt/user-data/uploads/report.pdf",
            "proposed_doc_id": "my-doc",
        },
    )

    def handler(req):
        return req.tool_call["args"]

    result = middleware.wrap_tool_call(request, handler)
    assert result["role"] == "finance"
    assert result["proposed_doc_id"] == "my-doc"
    assert result["file_path"].endswith("uploads/report.pdf")


# ── custom mount path ───────────────────────────────────────────────────


@pytest.mark.usefixtures("_patch_thread_id")
def test_custom_rag_data_mount(monkeypatch):
    monkeypatch.setenv("RAG_ORCHESTRATOR_DATA_MOUNT", "/custom/mount")
    mw = RagUploadPathMiddleware()

    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/report.pdf"},
    )

    def handler(req):
        return req.tool_call["args"]["file_path"]

    result = mw.wrap_tool_call(request, handler)
    assert result == f"/custom/mount/threads/{THREAD_ID}/user-data/uploads/report.pdf"


# ── async variant ────────────────────────────────────────────────────────


@pytest.mark.usefixtures("_patch_thread_id")
def test_awrap_tool_call_rewrites_path(middleware):
    import asyncio

    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/report.pdf"},
    )

    async def handler(req):
        return req.tool_call["args"]["file_path"]

    result = asyncio.run(middleware.awrap_tool_call(request, handler))
    assert result == f"/app/deer-flow-data/threads/{THREAD_ID}/user-data/uploads/report.pdf"


@pytest.mark.usefixtures("_patch_no_thread_id")
def test_awrap_missing_thread_id_returns_error(middleware):
    import asyncio

    request = DummyRequest(
        "rag_knowledge_base_inspect_uploaded_document",
        {"role": "default", "file_path": "/mnt/user-data/uploads/report.pdf"},
    )

    async def _noop(req):
        return "ok"

    result = asyncio.run(middleware.awrap_tool_call(request, _noop))

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
