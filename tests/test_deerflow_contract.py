from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

from app import ai_tools, deerflow_tools
from app.deerflow_worker import _config


class DeerFlowContractTests(unittest.TestCase):
    def tearDown(self) -> None:
        deerflow_tools.unbind_run()

    def test_trading_and_builtin_tools_are_denied(self) -> None:
        from deerflow.authz.provider import AuthzRequest, Principal

        allowed = frozenset({"mcp__finch__research"})
        self.assertNotIn("get_stock_dossier", allowed)
        self.assertNotIn("get_account_snapshot", allowed)
        state = deerflow_tools.RunState(object(), "owner-1", "AI-TEST", allowed, 8)
        deerflow_tools.bind_run(state)
        provider = deerflow_tools.ResearchAuthorization()
        principal = Principal(user_id="owner-1", attributes={"finch_run_id": "AI-TEST"})

        def verdict(name: str, actor: Principal = principal) -> bool:
            return provider.authorize(AuthzRequest(actor, "tool", "use", name)).allow

        self.assertTrue(verdict("mcp__finch__research"))
        for name in ("present_file", "ask_clarification", "place_paper_trade", "get_account_snapshot", "get_stock_dossier"):
            self.assertFalse(verdict(name), name)
        self.assertFalse(verdict("mcp__finch__research", Principal(user_id="other", attributes={"finch_run_id": "AI-TEST"})))
        self.assertFalse(verdict("mcp__finch__research", Principal(user_id="owner-1", attributes={"finch_run_id": "wrong"})))

    def test_watchlist_returns_only_real_cached_rows(self) -> None:
        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, sql):
                self.sql = sql
                return self

            def fetchall(self):
                return [{"instrument_id": "CN:002594", "name": "比亚迪", "last": 100.0,
                         "exchange_time": "2026-10-26T09:30:00", "provider": "fixture"}]

        connection = Connection()
        tools = ai_tools.ResearchTools(lambda _: {}, lambda _: None, lambda row: dict(row),
                                        lambda _: {}, lambda _: None, None)
        with patch.object(ai_tools, "_db", return_value=connection):
            result = asyncio.run(tools.execute("get_watchlist", {}))
        self.assertIn("LEFT JOIN quotes", connection.sql)
        self.assertEqual(result["instruments"][0]["instrument_id"], "CN:002594")
        self.assertEqual(result["instruments"][0]["exchange_time"], "2026-10-26T09:30:00")
        self.assertEqual(result["evidence"][0]["evidence_id"], "E001")

    def test_config_exposes_all_authorized_tools_without_keyword_gating(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {"DATA_DIR": directory, "MODEL_CONFIG_JSON":
                   '[{"provider":"openai","model":"test","base_url":"http://127.0.0.1:9999/v1"}]',
                   "PRIMARY_MODEL": "test"}
            with patch.dict(os.environ, env):
                allowed = frozenset({"mcp__finch__research"})
                path, name = _config({"question": "分析CN:002594今日操作建议"}, allowed)
                try:
                    import yaml
                    config = yaml.safe_load(path.read_text())
                finally:
                    path.unlink(missing_ok=True)
            self.assertEqual(name, "test")
            self.assertEqual({tool["name"] for tool in config["tools"]}, set(allowed))
            self.assertTrue(config["authorization"]["fail_closed"])
            self.assertFalse(config["sandbox"]["allow_host_bash"])
            self.assertFalse(config["subagents"]["enabled"])
            self.assertEqual(allowed, {"mcp__finch__research"})


if __name__ == "__main__":
    unittest.main()
