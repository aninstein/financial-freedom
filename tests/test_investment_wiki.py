"""The wiki editor must preserve owner isolation and published memory state."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import investment_memory as memory, investment_wiki as wiki
from app.mysql_db import connect


class InvestmentWikiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.old_env = {key: os.environ.get(key) for key in ("DATA_DIR", "MYSQL_PASSWORD", "MYSQL_PASSWORD_FILE", "CONTAINER_RUNTIME")}
        os.environ["DATA_DIR"] = self.temporary.name
        os.environ["CONTAINER_RUNTIME"] = "false"
        os.environ.pop("MYSQL_PASSWORD", None)
        os.environ.pop("MYSQL_PASSWORD_FILE", None)
        memory.initialize()
        self.owner = "wiki-alice"

    def tearDown(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temporary.cleanup()

    def test_tree_and_editable_markdown_are_owner_scoped(self) -> None:
        memory.ensure_space(self.owner)
        self.assertIn("index.md", [item["name"] for item in wiki.list_directory(self.owner)["items"]])
        doc = wiki.get_document(self.owner, "readme.md")
        changed = wiki.save_document(self.owner, "readme.md", "# 我的说明\n\n偏好低回撤。\n", doc["sha256"])
        self.assertIn("偏好低回撤", changed["content"])
        self.assertNotIn("偏好低回撤", wiki.get_document("wiki-bob", "readme.md")["content"])
        with self.assertRaisesRegex(Exception, "已更新"):
            wiki.save_document(self.owner, "readme.md", "# 过时修改", doc["sha256"])
        for bad in ("../readme.md", "/readme.md", "sessions/../../readme.md", ".index.md.manual"):
            with self.assertRaises(Exception):
                wiki.get_document(self.owner, bad)

    def test_index_and_summary_edits_survive_projection(self) -> None:
        session = memory.create_session(self.owner)["id"]
        message = memory.add_message(self.owner, session, "user", "今天研究ETF波动")
        day = message["local_date"]
        index = wiki.get_document(self.owner, "index.md")
        wiki.save_document(self.owner, "index.md", "# 我的投资目录\n\n重要研究放这里。\n", index["sha256"])
        memory.ensure_space(self.owner)
        self.assertIn("重要研究", wiki.get_document(self.owner, "index.md")["content"])
        log = wiki.get_document(self.owner, "log.md")
        wiki.save_document(self.owner, "log.md", "# 我的事件备注\n\n归档后核对来源。\n", log["sha256"])
        memory._log(memory.wiki_root(self.owner), "test", "note")
        memory._prune_log(memory.wiki_root(self.owner), day)
        self.assertIn("归档后核对来源", wiki.get_document(self.owner, "log.md")["content"])
        path = f"sessions/{day}/{session}.summary.md"
        summary = wiki.get_document(self.owner, path)
        edited = summary["content"] + "- 我会优先比较波动。\n"
        wiki.save_document(self.owner, path, edited, summary["sha256"])
        memory.project_session_day(self.owner, session, day)
        self.assertIn("优先比较波动", wiki.get_document(self.owner, path)["content"])

    def test_entry_and_daily_edits_update_agent_sources(self) -> None:
        session = memory.create_session(self.owner)["id"]
        message = memory.add_message(self.owner, session, "user", "今后我的投资建议默认先考虑最大回撤。")
        day = message["local_date"]
        with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))):
            asyncio.run(memory.archive_day(self.owner, day))
        entry = memory.list_entries(self.owner)[0]
        path = f"{entry['tier']}/{entry['entry_id']}.md"
        document = wiki.get_document(self.owner, path)
        prefix, _ = document["content"].split("\n---\n", 1)
        revised = prefix + "\n---\n\n今后优先控制最大回撤，并分散持仓。\n"
        wiki.save_document(self.owner, path, revised, document["sha256"])
        self.assertEqual(memory.get_entry(self.owner, entry["entry_id"])["status"], "confirmed")
        self.assertTrue(any("分散持仓" in item["text"] for item in memory.recall(self.owner, "回撤")["items"]))
        report_path = f"daily/{day}/report.md"
        report = wiki.get_document(self.owner, report_path)
        edited_report = report["content"].replace("## 主题与决策", "## 主题与决策\n\n- 用户补充：先看回撤。")
        updated = wiki.save_document(self.owner, report_path, edited_report, report["sha256"])
        self.assertIn("用户补充", updated["content"])
        self.assertEqual(memory.get_daily(self.owner, day)["version"], 2)
        with connect() as db:
            rows = db.execute("SELECT version FROM memory_archive_publications WHERE owner_id=? AND local_date=?", (self.owner, day)).fetchall()
        self.assertEqual(len(rows), 1)
        old = wiki.get_document(self.owner, f"daily/{day}/report-v1.md")
        self.assertFalse(old["editable"])
        with self.assertRaises(Exception):
            wiki.save_document(self.owner, old["path"], old["content"] + "旧版修改", old["sha256"])
        self.assertTrue(any("用户补充" in item["text"] for item in memory.recall(self.owner, "回撤")["items"] if item["tier"] == "daily"))
        with self.assertRaises(Exception):
            wiki.save_document(self.owner, report_path, edited_report.replace("## 来源索引", "## 伪造来源"), updated["sha256"])

    def test_api_never_uses_a_client_owner_id(self) -> None:
        app = FastAPI()
        app.include_router(wiki.router)
        client = TestClient(app)
        memory.ensure_space(self.owner)
        with patch.object(wiki.security, "current_owner_id", return_value=self.owner):
            self.assertEqual(client.get("/api/v1/ai/memory/wiki/tree").status_code, 200)
            self.assertEqual(client.get("/api/v1/ai/memory/wiki/file", params={"path": "readme.md"}).status_code, 200)
        with patch.object(wiki.security, "current_owner_id", return_value="wiki-bob"):
            self.assertNotIn("我的投资目录", client.get("/api/v1/ai/memory/wiki/file", params={"path": "index.md"}).json()["content"])


if __name__ == "__main__":
    unittest.main()
