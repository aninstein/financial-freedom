"""Behavioral checks for the owner-scoped investment wiki."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import investment_memory as memory
from app.mysql_db import connect


class InvestmentMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.old_data = os.environ.get("DATA_DIR")
        self.old_password = os.environ.pop("MYSQL_PASSWORD", None)
        self.old_password_file = os.environ.pop("MYSQL_PASSWORD_FILE", None)
        self.old_container_runtime = os.environ.get("CONTAINER_RUNTIME")
        os.environ["CONTAINER_RUNTIME"] = "false"
        os.environ["DATA_DIR"] = self.temporary.name
        memory.initialize()
        self.today = datetime.now(memory.TZ).date()

    def tearDown(self) -> None:
        if self.old_data is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self.old_data
        if self.old_password is not None:
            os.environ["MYSQL_PASSWORD"] = self.old_password
        if self.old_password_file is not None:
            os.environ["MYSQL_PASSWORD_FILE"] = self.old_password_file
        if self.old_container_runtime is None:
            os.environ.pop("CONTAINER_RUNTIME", None)
        else:
            os.environ["CONTAINER_RUNTIME"] = self.old_container_runtime
        self.temporary.cleanup()

    def at(self, offset: int, hour: int) -> str:
        day = self.today + timedelta(days=offset)
        return datetime(day.year, day.month, day.day, hour, tzinfo=memory.TZ).isoformat()

    def archive(self, owner: str, offset: int) -> dict:
        with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))):
            return asyncio.run(memory.archive_day(owner, (self.today + timedelta(days=offset)).isoformat()))

    def test_private_wiki_triad_cross_midnight_and_owner_scope(self) -> None:
        session = memory.create_session("alice")["id"]
        yesterday = (self.today - timedelta(days=1)).isoformat()
        today = self.today.isoformat()
        memory.add_message("alice", session, "user", "昨晚研究ETF", created_at=self.at(-1, 23))
        memory.add_message("alice", session, "assistant", "今天继续分析", created_at=self.at(0, 0))
        root = memory.wiki_root("alice")
        self.assertNotEqual(root, memory.wiki_root("bob"))
        for folder in (root, root / "sessions", root / "sessions" / yesterday,
                       root / "sessions" / today, root / "daily", root / "short-term", root / "long-term"):
            for filename in memory.TRIAD:
                self.assertTrue((folder / filename).is_file(), f"{folder}/{filename}")
        self.assertIn("昨晚研究ETF", (root / "sessions" / yesterday / f"{session}.jsonl").read_text())
        self.assertNotIn("昨晚研究ETF", (root / "sessions" / today / f"{session}.jsonl").read_text())
        with self.assertRaises(KeyError):
            memory.get_session("bob", session)
        self.assertFalse(memory.recall("bob", "ETF")["items"])

    def test_idempotent_messages_and_daily_versions(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        day = (self.today - timedelta(days=1)).isoformat()
        memory.add_message(owner, session, "user", "今天关注低波动ETF", message_id="client-unique-1",
                           created_at=self.at(-1, 12))
        memory.add_message(owner, session, "user", "今天关注低波动ETF", message_id="client-unique-1",
                           created_at=self.at(-1, 12))
        self.assertEqual(len(memory.get_session(owner, session)["messages"]), 1)
        first = self.archive(owner, -1)
        second = self.archive(owner, -1)
        self.assertEqual(first["version"], second["version"])
        memory.add_message(owner, session, "assistant", "补充了结论", created_at=self.at(-1, 13))
        with self.assertRaises(KeyError):
            memory.get_daily(owner, day)
        third = self.archive(owner, -1)
        self.assertEqual(third["version"], first["version"] + 1)
        self.assertEqual(memory.get_daily(owner, day)["version"], third["version"])

    def test_cross_session_recall_is_derived_and_inference_requires_sources(self) -> None:
        owner = "alice"
        utterance = "近期我只研究低波动ETF，不追高，分批建仓。私人标记XYZ"
        ids = [memory.create_session(owner)["id"] for _ in range(3)]
        memory.add_message(owner, ids[0], "user", utterance, created_at=self.at(-1, 11))
        memory.add_message(owner, ids[1], "user", utterance, created_at=self.at(-1, 15))
        self.archive(owner, -1)
        memory.add_message(owner, ids[2], "user", utterance, created_at=self.at(0, 10))
        self.archive(owner, 0)
        entries = memory.list_entries(owner)
        inferred = [item for item in entries if item["tier"] == "long-term" and item["status"] == "inferred"]
        self.assertEqual(len(inferred), 1)
        self.assertEqual(len(inferred[0]["source_refs"]), 3)
        self.assertNotIn("私人标记XYZ", inferred[0]["content"])
        recalled = memory.recall(owner, "低波动ETF", current_session_id=ids[2])
        self.assertTrue(recalled["items"])
        self.assertNotIn("私人标记XYZ", str(recalled))
        self.assertFalse(any(item["tier"] == "today-summary" and ids[2] in item["source"] for item in recalled["items"]))

    def test_deletion_invalidates_daily_and_removes_sole_sourced_memory(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        memory.add_message(owner, session, "user", "今后我的投资建议默认先考虑最大回撤。", created_at=self.at(-1, 12))
        self.archive(owner, -1)
        self.assertTrue(any(item["status"] == "explicit" for item in memory.list_entries(owner)))
        days = memory.delete_session(owner, session)
        self.assertEqual(days, [(self.today - timedelta(days=1)).isoformat()])
        with self.assertRaises(KeyError):
            memory.get_daily(owner, days[0])
        self.assertFalse(list((memory.wiki_root(owner) / "daily" / days[0]).glob("report*.md")))
        self.assertFalse(memory.list_entries(owner))
        self.archive(owner, -1)
        self.assertEqual(memory.get_daily(owner, days[0])["status"], "empty")

    def test_retention_hard_limit_keeps_a_degraded_archive(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        old_day = (self.today - timedelta(days=3)).isoformat()
        memory.add_message(owner, session, "user", "关注ETF和仓位", created_at=self.at(-3, 12))
        memory.update_settings(owner, session_days=1, archive_days=10)
        with self.assertRaises(KeyError):
            memory.get_session(owner, session)
        self.assertFalse((memory.wiki_root(owner) / "sessions" / old_day).exists())
        self.assertEqual(memory.get_daily(owner, old_day)["status"], "degraded")
        self.assertIn("归档缺口", memory.get_daily(owner, old_day)["content"])
        self.assertNotIn("关注ETF和仓位", memory.get_daily(owner, old_day)["content"])

    def test_failed_republish_keeps_verified_previous_version(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        day = (self.today - timedelta(days=1)).isoformat()
        memory.add_message(owner, session, "user", "观察ETF走势", created_at=self.at(-1, 12))
        self.archive(owner, -1)
        with connect() as db:
            db.execute("UPDATE memory_archive_jobs SET status='provisional' WHERE owner_id=? AND local_date=?", (owner, day))
            db.execute("UPDATE memory_archive_publications SET status='provisional' WHERE owner_id=? AND local_date=?", (owner, day))
        original_atomic = memory._atomic

        def fail_new_report(path: Path, content: str) -> None:
            if path.name == "report-v2.md":
                raise OSError("simulated interrupted write")
            original_atomic(path, content)

        with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))), \
             patch.object(memory, "_atomic", side_effect=fail_new_report):
            with self.assertRaises(OSError):
                asyncio.run(memory.archive_day(owner, day))
        self.assertEqual(memory.get_daily(owner, day)["status"], "provisional")
        self.assertTrue(any(item["tier"] == "daily" and item["date"] == day
                            for item in memory.recall(owner, "ETF")["items"]))
        self.assertEqual(self.archive(owner, -1)["version"], 2)
        self.assertEqual(memory.get_daily(owner, day)["status"], "published")

    def test_new_explicit_opposite_is_visible_as_conflict(self) -> None:
        owner = "alice"
        first = memory.create_session(owner)["id"]
        second = memory.create_session(owner)["id"]
        memory.add_message(owner, first, "user", "今后我的投资建议默认不追高。", created_at=self.at(-1, 11))
        self.archive(owner, -1)
        memory.add_message(owner, second, "user", "今后我的投资建议默认可以追高。", created_at=self.at(0, 11))
        self.archive(owner, 0)
        entries = memory.list_entries(owner)
        self.assertEqual({entry["status"] for entry in entries}, {"explicit", "conflicted"})
        self.assertEqual(len(memory.get_entry(owner, entries[0]["entry_id"])["source_refs"]), 1)
        with self.assertRaises(KeyError):
            memory.get_entry("bob", entries[0]["entry_id"])
        statuses = {item["status"] for item in memory.recall(owner, "追高")["items"]}
        self.assertIn("conflicted", statuses)
        self.assertIn("explicit", statuses)
        winner = next(entry for entry in entries if entry["status"] == "explicit")
        memory.update_entry(owner, winner["entry_id"], "我确认今后可以追高，但需要重新核对当日风险。")
        self.assertTrue(any(entry["status"] == "superseded" for entry in memory.list_entries(owner)))
        self.assertFalse(any(item["status"] == "superseded" for item in memory.recall(owner, "追高")["items"]))

    def test_finished_short_term_plan_stops_recall(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        memory.add_message(owner, session, "user", "今天关注比亚迪的走势", created_at=self.at(0, 10))
        self.archive(owner, 0)
        self.assertTrue(any(item["status"] == "active" for item in memory.list_entries(owner)))
        memory.add_message(owner, session, "user", "我已完成比亚迪的研究", created_at=self.at(0, 12))
        self.archive(owner, 0)
        self.assertTrue(any(item["status"] == "completed" for item in memory.list_entries(owner)))
        self.assertFalse(any(item["tier"] == "short-term" for item in memory.recall(owner, "比亚迪")["items"]))

    def test_novel_style_can_be_explicit_or_inferred(self) -> None:
        owner = "alice"
        explicit_session = memory.create_session(owner)["id"]
        memory.add_message(owner, explicit_session, "user", "今后我的投资建议默认先考虑现金流稳定的公司。", created_at=self.at(-1, 9))
        for index, offset in enumerate((-1, 0, 0)):
            session = memory.create_session(owner)["id"]
            memory.add_message(owner, session, "user", "我偏好现金流稳定的公司", created_at=self.at(offset, 10 + index))
        self.archive(owner, -1)
        self.archive(owner, 0)
        entries = memory.list_entries(owner)
        self.assertTrue(any(item["status"] == "explicit" and "现金流稳定" in item["content"] for item in entries))
        self.assertTrue(any(item["status"] == "inferred" and "现金流稳定" in item["content"] for item in entries))

    def test_scheduler_catches_up_due_day(self) -> None:
        owner = "alice"
        current = datetime.now(memory.TZ)
        offset = -1 if current.hour >= 3 else -2
        session = memory.create_session(owner)["id"]
        memory.add_message(owner, session, "user", "研究ETF波动", created_at=self.at(offset, 12))
        with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))):
            asyncio.run(memory.archive_due())
        due_day = (self.today + timedelta(days=offset)).isoformat()
        self.assertEqual(memory.get_daily(owner, due_day)["status"], "published")

    def test_legacy_import_never_becomes_confirmed_preference(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        memory.add_message(owner, session, "user", "今后我的投资建议默认先考虑最大回撤。",
                           provenance="legacy", created_at=self.at(0, 10))
        self.archive(owner, 0)
        self.assertFalse(memory.list_entries(owner))
        self.assertIn("来源不完整", memory.get_daily(owner, self.today.isoformat())["content"])
        self.assertEqual(memory.get_session(owner, session)["messages"][0]["provenance"], "legacy")

    def test_api_contract_scopes_sessions_and_settings_to_owner(self) -> None:
        app = FastAPI()
        app.include_router(memory.router)
        client = TestClient(app)
        with patch.object(memory.security, "current_owner_id", return_value="alice"):
            created = client.post("/api/v1/ai/sessions", json={"title": "我的投研"})
            self.assertEqual(created.status_code, 201)
            session_id = created.json()["id"]
            self.assertEqual(client.get("/api/v1/ai/sessions").json()[0]["id"], session_id)
            self.assertEqual(client.get(f"/api/v1/ai/sessions/{session_id}").status_code, 200)
            self.assertEqual(client.patch("/api/v1/ai/memory/settings", json={"session_days": 0, "archive_days": 365}).status_code, 422)
            updated = client.patch("/api/v1/ai/memory/settings", json={"session_days": 7, "archive_days": 90})
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["session_days"], 7)
            self.assertEqual(updated.json()["wiki_path"], str(memory.wiki_root("alice")))
            self.assertTrue(updated.json()["wiki_exists"])
        with patch.object(memory.security, "current_owner_id", return_value="bob"):
            self.assertEqual(client.get(f"/api/v1/ai/sessions/{session_id}").status_code, 404)
            self.assertEqual(client.delete(f"/api/v1/ai/sessions/{session_id}").status_code, 404)
            self.assertNotEqual(client.get("/api/v1/ai/memory/settings").json()["wiki_path"],
                                str(memory.wiki_root("alice")))

    def test_deleting_during_archive_cannot_publish_deleted_content(self) -> None:
        owner = "alice"
        session = memory.create_session(owner)["id"]
        memory.add_message(owner, session, "user", "今后我的投资建议默认先考虑最大回撤。", created_at=self.at(0, 10))
        day = self.today.isoformat()

        async def scenario() -> None:
            started = asyncio.Event()
            resume = asyncio.Event()

            async def paused_digest(_rows, _day, _summaries):
                started.set()
                await resume.wait()
                return [], "published"

            with patch.object(memory, "_digest", side_effect=paused_digest):
                running = asyncio.create_task(memory.archive_day(owner, day))
                await started.wait()
                memory.delete_session(owner, session)
                resume.set()
                with self.assertRaises(RuntimeError):
                    await running

        asyncio.run(scenario())
        with self.assertRaises(KeyError):
            memory.get_daily(owner, day)
        self.assertFalse(memory.list_entries(owner))
        self.assertFalse(list((memory.wiki_root(owner) / "daily" / day).glob("report*.md")))


if __name__ == "__main__":
    unittest.main()
