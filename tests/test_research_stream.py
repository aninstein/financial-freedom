"""Research progress remains incremental and final content stays authoritative."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from app import deerflow_bridge, main
from app.deerflow_worker import collect_stream_answer


class ResearchStreamTests(unittest.TestCase):
    def test_worker_stream_selects_last_public_message(self):
        events = [
            SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "draft", "content": "查询前的文字"}),
            SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "draft", "tool_calls": [{"name": "get_watchlist"}], "content": ""}),
            SimpleNamespace(type="messages-tuple", data={"type": "tool", "name": "get_watchlist", "content": "private result"}),
            SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "final", "content": "最终"}),
            SimpleNamespace(type="messages-tuple", data={"type": "ai", "id": "final", "content": "回答", "additional_kwargs": {"reasoning_content": "private"}}),
        ]
        progress = []
        answer = collect_stream_answer(events, progress.append)
        self.assertEqual(answer, "最终回答")
        self.assertEqual([item["type"] for item in progress],
                         ["answer_reset", "answer_delta", "answer_reset", "answer_delta", "answer_delta"])
        self.assertNotIn("private", json.dumps(progress))

    def test_unix_bridge_forwards_events_before_final_result(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "worker.sock"

                async def handler(reader, writer):
                    request = json.loads(await reader.readline())
                    self.assertTrue(request["stream"])
                    writer.write(b'{"event":{"type":"status","message":"working"}}\n')
                    await writer.drain()
                    writer.write(b'{"ok":true,"result":{"answer":"done","evidence":[]}}\n')
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()

                server = await asyncio.start_unix_server(handler, str(path))
                seen = []
                async with server:
                    with patch.object(deerflow_bridge, "runtime_ready", return_value=True), \
                         patch.object(deerflow_bridge, "socket_path", return_value=path):
                        result = await deerflow_bridge.run_deerflow_research(
                            run_id="AI-TEST", owner_id="owner", question="分析持仓", history=[],
                            max_tool_calls=4, timeout=5, on_event=lambda event: append_event(seen, event),
                        )
                self.assertEqual(seen[0]["message"], "working")
                self.assertEqual(result["answer"], "done")

        async def append_event(target, event):
            target.append(event)

        asyncio.run(scenario())

    def test_sse_route_emits_progress_and_done(self):
        async def scenario():
            async def research(_request, _http_request, emit):
                await emit({"type": "status", "message": "查询行情"})
                await emit({"type": "answer_delta", "text": "结论"})
                return {"answer": "结论", "evidence": []}

            with patch.object(main, "_ai_research", side_effect=research):
                response = await main.ai_research_stream(main.AIResearchRequest(question="分析持仓"), SimpleNamespace())
                chunks = [chunk async for chunk in response.body_iterator]
            events = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks]
            self.assertEqual([event["type"] for event in events], ["status", "answer_delta", "done"])
            self.assertEqual(events[-1]["result"]["answer"], "结论")

        asyncio.run(scenario())

    def test_sse_route_reports_failure_without_hanging(self):
        async def scenario():
            async def research(_request, _http_request, emit):
                await emit({"type": "status", "message": "准备中"})
                raise HTTPException(422, "账户未登记")

            with patch.object(main, "_ai_research", side_effect=research):
                response = await main.ai_research_stream(main.AIResearchRequest(question="分析持仓"), SimpleNamespace())
                events = [json.loads(chunk.removeprefix("data: ").strip()) async for chunk in response.body_iterator]
            self.assertEqual([event["type"] for event in events], ["status", "error"])
            self.assertEqual(events[-1]["message"], "账户未登记")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
