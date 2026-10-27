"""Warm, single-run-at-a-time local DeerFlow worker over a private Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.deerflow_bridge import socket_path
from app.deerflow_worker import execute


async def serve() -> None:
    # Import the heavy runtime before publishing the socket as ready.
    from deerflow.client import DeerFlowClient  # noqa: F401

    path = socket_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists():
        if path.is_socket():
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.settimeout(1)
                probe.connect(str(path))
            except OSError:
                pass
            else:
                raise RuntimeError("DeerFlow worker is already running")
            finally:
                probe.close()
            path.unlink()
        else:
            raise RuntimeError("DeerFlow socket path is occupied by a non-socket file")
    lock = asyncio.Lock()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await reader.readline()
            if not line:
                return
            if len(line) > 8_000_000:
                raise ValueError("request_too_large")
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("invalid_request")
            async with lock:
                print(f"finch deerflow start run={request.get('run_id')}", file=sys.stderr, flush=True)
                if request.get("stream"):
                    events: asyncio.Queue[dict] = asyncio.Queue()
                    loop = asyncio.get_running_loop()

                    def progress(event: dict) -> None:
                        loop.call_soon_threadsafe(events.put_nowait, event)

                    work = asyncio.create_task(asyncio.to_thread(execute, request, progress))
                    while not work.done() or not events.empty():
                        try:
                            event = await asyncio.wait_for(events.get(), timeout=0.1)
                        except asyncio.TimeoutError:
                            continue
                        writer.write(json.dumps({"event": event}, ensure_ascii=False).encode() + b"\n")
                        await writer.drain()
                    result = await work
                else:
                    result = await asyncio.to_thread(execute, request)
                print(f"finch deerflow done run={request.get('run_id')} calls={result.get('tool_calls')}", file=sys.stderr, flush=True)
            response = {"ok": True, "result": result}
        except Exception as exc:
            print(f"finch deerflow error type={type(exc).__name__}", file=sys.stderr, flush=True)
            response = {"ok": False, "error": type(exc).__name__}
        writer.write(json.dumps(response, ensure_ascii=False, default=str).encode() + b"\n")
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=str(path), limit=8_000_000)
    path.chmod(0o600)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        async with server:
            await stop.wait()
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    os.umask(0o077)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    asyncio.run(serve())
