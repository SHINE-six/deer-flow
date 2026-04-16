import os

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api", tags=["mcp"])

RAG_MCP_UPSTREAM = os.getenv("RAG_MCP_UPSTREAM", "http://rag-orchestrator:9620/mcp")
_TIMEOUT = httpx.Timeout(60.0, connect=5.0)
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _build_upstream_url(path: str, query: str) -> str:
    base = RAG_MCP_UPSTREAM.rstrip("/")
    # Always append "/" when no sub-path so Starlette Mount receives "/" not "".
    suffix = f"/{path.lstrip('/')}" if path else "/"
    return f"{base}{suffix}?{query}" if query else f"{base}{suffix}"


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }


async def _proxy_request(request: Request, path: str = "") -> Response:
    upstream_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    # FastMCP rejects the Docker service DNS name in Host for streamable HTTP.
    # Canonicalize it at the gateway boundary instead of inside the app.
    upstream_headers["host"] = "127.0.0.1:9620"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        upstream_response = await client.request(
            method=request.method,
            url=_build_upstream_url(path, request.url.query),
            headers=upstream_headers,
            content=await request.body(),
        )

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_filter_response_headers(upstream_response.headers),
        media_type=upstream_response.headers.get("content-type"),
    )


@router.api_route("/rag-mcp", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy_rag_mcp_root(request: Request) -> Response:
    return await _proxy_request(request)


@router.api_route("/rag-mcp/{path:path}", methods=["GET", "POST", "DELETE", "OPTIONS"])
async def proxy_rag_mcp_path(path: str, request: Request) -> Response:
    return await _proxy_request(request, path=path)
