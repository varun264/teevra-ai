"""TEEVRA AI A2A helper: AgentCard + JSON-RPC tasks/send server and client.

Standards-compatible A2A (agent2agent) over HTTP. Uses the official a2a-sdk
protobuf types for AgentCard/Task/Message and httpx for client requests.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from google.protobuf.json_format import MessageToDict
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import a2a.types as t


def new_id() -> str:
    return uuid.uuid4().hex


_MSG_ROLE_AGENT = t.Message.DESCRIPTOR.fields_by_name["role"].enum_type.values_by_name["ROLE_AGENT"].number


def build_agent_card(
    name: str,
    description: str,
    version: str = "1.0.0",
    url: str = "",
) -> t.AgentCard:
    card = t.AgentCard(
        name=name,
        description=description,
        version=version,
        documentation_url=url or "",
    )
    card.capabilities.streaming = False
    card.capabilities.push_notifications = False
    card.default_input_modes.append("text")
    card.default_output_modes.append("text")
    return card


def agent_card_to_json(card: t.AgentCard) -> dict[str, Any]:
    return MessageToDict(card, preserving_proto_field_name=True)


def _make_text_part(text: str) -> t.Part:
    part = t.Part()
    part.text = text
    return part


def build_task(
    task_id: str,
    context_id: str,
    text: str,
    state: str = "completed",
) -> t.Task:
    task = t.Task()
    task.id = task_id
    task.context_id = context_id
    state_name = state.upper()
    if not state_name.startswith("TASK_STATE_"):
        state_name = "TASK_STATE_" + state_name
    task.status.state = t.TaskState.Value(state_name)
    msg = task.history.add()
    msg.message_id = new_id()
    msg.role = _MSG_ROLE_AGENT
    part = _make_text_part(text)
    msg.parts.add().CopyFrom(part)
    return task


def task_to_json(task: t.Task) -> dict[str, Any]:
    return MessageToDict(task, preserving_proto_field_name=True)


# --------------------------------------------------------------------------- #
# FastAPI A2A app
# --------------------------------------------------------------------------- #
# Handler: (message_text, context_id, task_id, correlation_id, headers) -> str
A2AHandler = Callable[[str, str, str, str, dict[str, str]], str]


def create_a2a_app(agent_card: t.AgentCard, handler: A2AHandler) -> FastAPI:
    app = FastAPI(title=f"A2A: {agent_card.name}")

    @app.get("/.well-known/agent.json")
    async def agent_card_endpoint():
        return JSONResponse(content=agent_card_to_json(agent_card))

    @app.post("/")
    async def a2a_endpoint(request: Request):
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {}) or {}
        req_id = body.get("id")

        if method == "tasks/send":
            try:
                message = params.get("message", {})
                parts = message.get("parts", [])
                text = ""
                for p in parts:
                    if p.get("text"):
                        text += p["text"]
                task_id = params.get("id") or new_id()
                context_id = message.get("context_id") or new_id()
                correlation_id = (
                    request.headers.get("x-correlation-id")
                    or request.headers.get("X-Correlation-ID")
                    or new_id()
                )
                import inspect
                result_or_coro = handler(
                    text, context_id, task_id, correlation_id, dict(request.headers)
                )
                if inspect.isawaitable(result_or_coro):
                    result_text = await result_or_coro
                else:
                    result_text = result_or_coro
                task = build_task(task_id, context_id, result_text, state="completed")
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": task_to_json(task),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32603,
                            "message": f"internal error: {exc}",
                        },
                    },
                )

        if method == "tasks/get":
            task_id = params.get("id") or new_id()
            context_id = params.get("context_id") or new_id()
            task = build_task(task_id, context_id, "", state="completed")
            return JSONResponse(
                content={"jsonrpc": "2.0", "id": req_id, "result": task_to_json(task)}
            )

        return JSONResponse(
            status_code=404,
            content={
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            },
        )

    return app


# --------------------------------------------------------------------------- #
# A2A remote client
# --------------------------------------------------------------------------- #
class A2ARemoteClient:
    """HTTP A2A client that sends tasks/send to a remote agent."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 60.0,
        auth_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.auth_token = auth_token
        self._client: Optional[httpx.AsyncClient] = None

    async def _client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers: dict[str, str] = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    async def get_agent_card(self) -> dict[str, Any]:
        cl = await self._client()
        resp = await cl.get(f"{self.base_url}/.well-known/agent.json")
        resp.raise_for_status()
        return resp.json()

    async def send_task(
        self,
        message_text: str,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        context_id = context_id or new_id()
        task_id = task_id or new_id()
        correlation_id = correlation_id or new_id()
        cl = await self._client()
        payload = {
            "jsonrpc": "2.0",
            "id": new_id(),
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "context_id": context_id,
                "message": {
                    "message_id": new_id(),
                    "context_id": context_id,
                    "task_id": task_id,
                    "role": "user",
                    "parts": [{"text": message_text}],
                },
                "metadata": {"correlation_id": correlation_id},
            },
        }
        headers = {"Content-Type": "application/json"}
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        resp = await cl.post(f"{self.base_url}/", json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"A2A error: {body['error']}")
        return body.get("result", {})

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()

    async def __aenter__(self):
        await self._client()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()


__all__ = [
    "build_agent_card",
    "agent_card_to_json",
    "build_task",
    "task_to_json",
    "create_a2a_app",
    "A2ARemoteClient",
    "new_id",
]
