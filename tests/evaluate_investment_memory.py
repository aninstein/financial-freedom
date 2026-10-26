"""Deterministic, synthetic recall baseline; no model or market network calls."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from app import investment_memory as memory


def run() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        old = {name: os.environ.get(name) for name in ("DATA_DIR", "MYSQL_PASSWORD", "MYSQL_PASSWORD_FILE", "CONTAINER_RUNTIME")}
        os.environ["DATA_DIR"] = directory
        os.environ["CONTAINER_RUNTIME"] = "false"
        os.environ.pop("MYSQL_PASSWORD", None)
        os.environ.pop("MYSQL_PASSWORD_FILE", None)
        try:
            memory.initialize()
            owner = "evaluation-owner"
            today = datetime.now(memory.TZ).date()

            def at(days: int, hour: int) -> str:
                day = today + timedelta(days=days)
                return datetime(day.year, day.month, day.day, hour, tzinfo=memory.TZ).isoformat()

            sessions = [memory.create_session(owner)["id"] for _ in range(7)]
            for index, day in enumerate((-1, -1, 0)):
                memory.add_message(owner, sessions[index], "user",
                                   "我偏好现金流稳定的公司。私人标记EVALXYZ", created_at=at(day, 9 + index))
            for index, day in enumerate((-1, 0, 0), start=3):
                memory.add_message(owner, sessions[index], "user",
                                   "今天关注比亚迪", created_at=at(day, 10 + index))
            memory.add_message(owner, sessions[6], "user", "今后我的投资建议默认不追高。", created_at=at(-1, 15))
            memory.add_message(owner, sessions[6], "user", "今后我的投资建议默认可以追高。", created_at=at(0, 16))
            with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))):
                asyncio.run(memory.archive_day(owner, (today - timedelta(days=1)).isoformat()))
                asyncio.run(memory.archive_day(owner, today.isoformat()))
            items = memory.recall(owner, "现金流 投资风格 比亚迪 追高", current_session_id=sessions[6])["items"]
            entries = memory.list_entries(owner)
            long_items = [entry for entry in entries if entry["tier"] == "long-term"]
            results = {
                "fixture_messages": 8,
                "historical_daily_hit": any(item["tier"] == "daily" and item["date"] == (today - timedelta(days=1)).isoformat() for item in items),
                "today_cross_session_hit": any(item["tier"] == "today-summary" for item in items),
                "inferred_style_hit": any(entry["status"] == "inferred" and "现金流稳定" in entry["content"] for entry in long_items),
                "topical_false_promotions": sum("比亚迪" in entry["content"] for entry in long_items),
                "conflict_visible": {"explicit", "conflicted"}.issubset({item["status"] for item in items}),
                "source_trace_rate": sum(bool(item.get("source")) and (item["tier"] in {"daily", "today-summary"} or bool(item.get("source_refs"))) for item in items) / max(1, len(items)),
                "raw_marker_leaks": str(items).count("私人标记EVALXYZ"),
                "recalled_items": len(items),
                "context_chars": sum(len(item["text"]) for item in items),
            }
            assert results["context_chars"] <= 2800
            return results
        finally:
            for name, value in old.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
