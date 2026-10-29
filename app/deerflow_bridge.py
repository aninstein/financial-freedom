"""Async local-socket bridge to the pinned Python 3.12 DeerFlow service."""

from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.ai_agent import AgentUnavailable


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PYTHON = ROOT / "runtime" / ".venv" / "bin" / "python"
MAX_RESPONSE_BYTES = 8_000_000


def socket_path() -> Path:
    return Path(os.getenv("DATA_DIR", ROOT / "data")).resolve() / "deerflow" / "worker.sock"


def runtime_ready() -> bool:
    if os.getenv('CONTAINER_RUNTIME') == 'true':
        return socket_path().is_socket()
    installed = (
        RUNTIME_PYTHON.is_file()
        and os.access(RUNTIME_PYTHON, os.X_OK)
        and (ROOT / "runtime" / ".ready").is_file()
        and socket_path().is_socket()
    )
    if not installed:
        return False
    try:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(0.5)
            probe.connect(str(socket_path()))
        return True
    except OSError:
        return False


async def run_deerflow_research(
    *, run_id: str, owner_id: str, question: str, history: list[dict[str, str]],
    max_tool_calls: int, timeout: float,
    session_id: str | None = None,
    image_data_url: str | None = None,
    image_id: str | None = None,
    image_context_available: bool = False,
    private_input: str | None = None,
    current_message: str | None = None,
    reauth_valid: bool = False,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    if not runtime_ready():
        raise AgentUnavailable("DeerFlow 尚未就绪；请运行 ./scripts/setup-deerflow.sh 并重启 ./run-local.sh")
    payload = {
        "run_id": run_id, "owner_id": owner_id, "question": question,
        "history": history, "max_tool_calls": max_tool_calls,
        "session_id": session_id,
        "image_id": image_id,
        "image_data_url": image_data_url,
        "image_context_available": image_context_available,
        "private_input": private_input,
        "current_message": current_message,
        "reauth_valid": reauth_valid,
        "stream": on_event is not None,
    }

    async def exchange() -> dict[str, Any]:
        # Tool evidence is returned as one JSON line. The asyncio default
        # 64 KiB line limit can reject an otherwise completed research run.
        reader, writer = await asyncio.open_unix_connection(
            str(socket_path()), limit=MAX_RESPONSE_BYTES
        )
        try:
            writer.write(json.dumps(payload, ensure_ascii=False, default=str).encode() + b"\n")
            await writer.drain()
            while True:
                line = await reader.readline()
                if not line:
                    raise AgentUnavailable("DeerFlow worker 已断开")
                response = json.loads(line)
                if "event" in response:
                    if on_event and isinstance(response["event"], dict):
                        await on_event(response["event"])
                    continue
                break
            if not response.get("ok"):
                raise AgentUnavailable("DeerFlow 运行失败：" + str(response.get("error", "RuntimeError")))
            result = response.get("result")
            if not isinstance(result, dict):
                raise AgentUnavailable("DeerFlow 返回格式无效")
            return result
        finally:
            writer.close()
            await writer.wait_closed()

    try:
        return await asyncio.wait_for(exchange(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise AgentUnavailable("Agent 任务超时") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentUnavailable("DeerFlow worker 连接失败") from exc
    except ValueError as exc:
        raise AgentUnavailable("DeerFlow 返回内容超过传输上限，请缩小问题范围后重试") from exc
