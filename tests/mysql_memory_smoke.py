"""Run against an isolated MySQL database named by MYSQL_DATABASE."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app import investment_memory as memory, investment_wiki as wiki


def main() -> None:
    memory.initialize()
    owner = "memory-mysql-smoke"
    session = memory.create_session(owner)["id"]
    message = memory.add_message(owner, session, "user", "今后我的投资建议默认先考虑最大回撤。")
    assert message["session_id"] == session
    with patch.object(memory, "_digest", new=AsyncMock(return_value=([], "published"))):
        archived = asyncio.run(memory.archive_day(owner, memory.local_day()))
    assert archived["status"] == "provisional"
    assert memory.get_daily(owner, memory.local_day())["version"] == 1
    settings = memory.get_settings(owner)
    assert settings["earliest_session_day"] == memory.local_day()
    assert settings["earliest_archive_day"] == memory.local_day()
    assert memory.get_entry(owner, memory.list_entries(owner)[0]["entry_id"])["status"] == "explicit"
    assert memory.recall(owner, "最大回撤")["items"]
    original = wiki.get_document(owner, "readme.md")
    assert "MySQL wiki smoke" in wiki.save_document(owner, "readme.md", "# MySQL wiki smoke\n", original["sha256"])["content"]
    report = wiki.get_document(owner, f"daily/{memory.local_day()}/report.md")
    revised = report["content"].replace("## 主题与决策", "## 主题与决策\n\n- 用户补充：重视回撤。")
    assert wiki.save_document(owner, report["path"], revised, report["sha256"])["sha256"]
    assert memory.get_daily(owner, memory.local_day())["version"] == 2
    print("MySQL investment memory smoke passed")


if __name__ == "__main__":
    main()
