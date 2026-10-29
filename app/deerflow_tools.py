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
from typing import Any, Callable

from langchain_core.tools import StructuredTool

from app import agent_extensions


@dataclass
class RunState:
    tools: Any
    owner_id: str
    run_id: str
    allowed: frozenset[str]
    max_calls: int
    session_id: str | None = None
    image_id: str | None = None
    private_input: str | None = None
    current_message: str | None = None
    reauth_valid: bool = False
    skill_names: frozenset[str] = frozenset()
    progress: Callable[[dict[str, Any]], None] | None = None
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
            return json.dumps({"error": "达到本轮工具调用上限，请基于已有结果回答并说明未完成的部分"}, ensure_ascii=False)
        state.calls += 1
        print(f"finch deerflow tool run={state.run_id} number={state.calls} name={name}", file=sys.stderr, flush=True)
    if state.progress:
        state.progress({"type": "tool_start", "name": name, "number": state.calls})
    try:
        if name == 'activate_skill':
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
            if name in {'mcp__finch__prepare_holdings_import', 'mcp__finch__research'}:
                args = {**args, 'session_id': state.session_id}
                if name == 'mcp__finch__prepare_holdings_import' and state.image_id:
                    args['image_id'] = state.image_id
            elif name == 'mcp__finch__manage_extension':
                args = {**args, 'private_input': state.private_input,
                        'current_message': state.current_message,
                        'reauth_valid': state.reauth_valid}
            result = asyncio.run(agent_extensions.call_mcp_tool(name, args, state.owner_id))
            if not result.get('isError'):
                evidence = state.tools._evidence('mcp_tool', f"{result['server']} / {result['tool']}",
                                                 f"MCP: {result['server']}", None, result)
                result = {'evidence': [evidence], **result}
        else:
            raise PermissionError('未提供此工具；平台能力只能经已授权 MCP 调用')
    except Exception as exc:
        result = {"error": f"工具不可用：{type(exc).__name__}"}
    if state.progress:
        state.progress({"type": "tool_end", "name": name, "number": state.calls,
                        "ok": "error" not in result})
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
