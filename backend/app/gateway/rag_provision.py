"""
Best-effort RAG workspace/role provisioning webhook.

Called by the agents router after CRUD operations.
Never blocks or fails the caller — all errors are logged and swallowed.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RAG_ORCHESTRATOR_URL = os.getenv(
    "RAG_ORCHESTRATOR_URL", "http://rag-orchestrator:9620"
)

# Short timeout — fire-and-forget, don't hold up agent creation
_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


async def provision_rag_workspace(agent_name: str) -> None:
    """Best-effort: create workspace + role for agent in RAG Orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{RAG_ORCHESTRATOR_URL}/provision",
                json={"agent_name": agent_name, "shared_read": True},
            )
            if resp.status_code == 200:
                logger.info("RAG provisioned for agent '%s': %s", agent_name, resp.json())
            else:
                logger.warning(
                    "RAG provision returned %d for '%s': %s",
                    resp.status_code, agent_name, resp.text,
                )
    except Exception as e:
        logger.warning("RAG provision failed for '%s' (non-fatal): %s", agent_name, e)


async def deprovision_rag_workspace(agent_name: str) -> None:
    """Best-effort: remove role (preserve data) for agent in RAG Orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{RAG_ORCHESTRATOR_URL}/deprovision",
                json={"agent_name": agent_name},
            )
            if resp.status_code == 200:
                logger.info("RAG deprovisioned for agent '%s': %s", agent_name, resp.json())
            else:
                logger.warning(
                    "RAG deprovision returned %d for '%s': %s",
                    resp.status_code, agent_name, resp.text,
                )
    except Exception as e:
        logger.warning("RAG deprovision failed for '%s' (non-fatal): %s", agent_name, e)
