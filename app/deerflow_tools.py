"""Narrow, per-process tool bridge for the embedded DeerFlow research worker.

This module is imported only by the isolated Python 3.12 worker. The model sees
only explicitly configured research tools; authorization rejects DeerFlow's
generic built-ins as well as any tool outside the server-selected set.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import StructuredTool

from app.ai_agent import TOOL_DEFINITIONS


@dataclass
class RunState:
    tools: Any
    owner_id: str
    run_id: str
    allowed: frozenset[str]
    max_calls: int
    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


_state: RunState | None = None


def bind_run(state: RunState) -> None:
    global _state
    if _state is not None:
        raise RuntimeError("DeerFlow worker already has a bound run")
    _state = state


def unbind_run() -> None:
    global _state
    _state = None


def _execute(name: str, args: dict[str, Any]) -> str:
    state = _state
    if state is None or name not in state.allowed:
        raise PermissionError("Research tool is not authorized for this run")
    with state.lock:
        if state.calls >= state.max_calls:
            print(f"finch deerflow tool_limit run={state.run_id} name={name}", file=sys.stderr, flush=True)
            return json.dumps({"error": "达到本轮工具调用上限，请使用已有证据给出操作建议"}, ensure_ascii=False)
        state.calls += 1
        print(f"finch deerflow tool run={state.run_id} number={state.calls} name={name}", file=sys.stderr, flush=True)
    try:
        result = asyncio.run(state.tools.execute(name, args))
    except Exception as exc:
        result = {"error": f"工具不可用：{type(exc).__name__}"}
    return json.dumps(result, ensure_ascii=False, default=str)[:24000]


def _make_tool(definition: dict[str, Any]) -> StructuredTool:
    spec = definition["function"]
    name = spec["name"]

    def call(**kwargs: Any) -> str:
        return _execute(name, kwargs)

    return StructuredTool.from_function(
        func=call,
        name=name,
        description=spec["description"],
        args_schema=spec["parameters"],
        infer_schema=False,
    )


for _definition in TOOL_DEFINITIONS:
    _tool = _make_tool(_definition)
    globals()[_tool.name] = _tool


class ResearchAuthorization:
    """DeerFlow's assembly and execution gate for this server-bound run."""

    name = "finch-research-only"

    def __init__(self, **_: Any) -> None:
        pass

    def authorize(self, request: Any) -> Any:
        from deerflow.authz.provider import AuthzDecision

        state = _state
        principal = request.principal
        bound = bool(
            state
            and principal.user_id == state.owner_id
            and principal.attributes.get("finch_run_id") == state.run_id
        )
        allow = False
        if bound and request.resource == "tool":
            allow = request.target in state.allowed
        elif bound and request.resource in {"model", "sandbox"}:
            allow = True
        return AuthzDecision(allow=allow, policy_id="finch-research-v1")

    async def aauthorize(self, request: Any) -> Any:
        return self.authorize(request)

    def filter_resources(self, principal: Any, resource_type: str, candidates: list[str]) -> list[str]:
        from deerflow.authz.provider import AuthzRequest

        return [
            item for item in candidates
            if self.authorize(AuthzRequest(principal=principal, resource=resource_type, action="use", target=item)).allow
        ]
