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
from app import agent_extensions
from app import investment_memory as memory


@dataclass
class RunState:
    tools: Any
    owner_id: str
    run_id: str
    allowed: frozenset[str]
    max_calls: int
    skill_names: frozenset[str] = frozenset()
    activated_skills: set[str] = field(default_factory=set)
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
        if name == 'get_investment_memory':
            try:
                result = memory.recall(state.owner_id, str(args.get('query') or ''), limit=10)
            except Exception:
                result = {'items': [], 'memory_status': 'degraded',
                          'notice': '投资记忆当前不可用；不要声称记得用户历史偏好。'}
        elif name == 'get_memory_entry':
            result = memory.get_entry(state.owner_id, str(args.get('entry_id') or ''))
        elif name == 'activate_skill':
            chosen = str(args.get('name', ''))
            if chosen not in state.skill_names:
                raise ValueError('Skill 未安装')
            state.activated_skills.add(chosen)
            result = {'name': chosen, 'instructions': agent_extensions.read_skill(chosen)[:16000]}
        elif name == 'read_skill_file':
            chosen = str(args.get('name', ''))
            if chosen not in state.activated_skills:
                raise ValueError('请先激活此 Skill')
            result = {'name': chosen, 'path': args.get('path'),
                      'content': agent_extensions.read_skill(chosen, str(args.get('path', '')))[:16000]}
        elif name.startswith('mcp__'):
            result = asyncio.run(agent_extensions.call_mcp_tool(name, args))
            evidence = state.tools._evidence('mcp_tool', f"{result['server']} / {result['tool']}",
                                             f"MCP: {result['server']}", None, result)
            result = {'evidence': [evidence], **result}
        else:
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


def register_extension_tools(definitions: list[dict[str, Any]]) -> None:
    """Publish only the tools selected for the current isolated run."""
    for definition in definitions:
        tool = _make_tool(definition)
        globals()[tool.name] = tool


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
