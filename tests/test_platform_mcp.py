"""The built-in platform MCP and browser state share owner-scoped records."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app import futu_trade, holdings, main, paper, platform_mcp, platform_workspace
from app.mysql_db import connect


class PlatformMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old = {name: os.environ.get(name) for name in ("DATA_DIR", "MYSQL_PASSWORD", "MYSQL_PASSWORD_FILE", "CONTAINER_RUNTIME")}
        os.environ["DATA_DIR"] = self.tmp.name
        os.environ["CONTAINER_RUNTIME"] = "false"
        os.environ.pop("MYSQL_PASSWORD", None)
        os.environ.pop("MYSQL_PASSWORD_FILE", None)
        platform_workspace.initialize()

    def tearDown(self) -> None:
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def test_card_mutation_is_owner_scoped_and_versioned(self) -> None:
        first = asyncio.run(platform_mcp.read("owner-a", "cards"))
        self.assertEqual(first["version"], 0)
        created = asyncio.run(platform_mcp.write("owner-a", "cards", "create_note", {
            "expected_version": 0, "title": "投研提醒", "body": "**核对财报**"}))
        self.assertEqual(created["version"], 1)
        note_id = next(key for key in created["custom_cards"])
        self.assertIn(note_id, created["cards"])
        self.assertEqual(asyncio.run(platform_mcp.read("owner-b", "cards"))["custom_cards"], {})
        with self.assertRaises(HTTPException) as stale:
            asyncio.run(platform_mcp.write("owner-a", "cards", "delete_note", {
                "expected_version": 0, "id": note_id}))
        self.assertEqual(stale.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            platform_workspace.put_state("owner-a", "cards", {"cards": ["unknown"]}, 1)

    def test_calendar_mutation_and_raw_session_denial(self) -> None:
        created = asyncio.run(platform_mcp.write("owner-a", "calendar", "create", {
            "expected_version": 0, "kind": "subscription", "item": {
                "name": "截图同步", "category": "持仓截图同步", "remindAt": "22:00", "enabled": True}}))
        self.assertEqual(created["subscriptions"][0]["remindAt"], "22:00")
        self.assertEqual(asyncio.run(platform_mcp.read("owner-b", "calendar"))["subscriptions"], [])
        with self.assertRaises(HTTPException) as blocked:
            asyncio.run(platform_mcp.read("owner-a", "wiki_file", {"path": "sessions/2026-10-27/a.summary.md"}))
        self.assertEqual(blocked.exception.status_code, 403)
        self.assertNotIn("orders", platform_mcp.catalog()["writable"])

    def test_holdings_import_tool_saves_owner_scoped_review_draft_only(self) -> None:
        holdings.initialize()
        preview = {"currency": "CNY", "positions": [{"instrument_id": None, "name": "示例基金",
                   "asset_class": "fund", "quantity": None, "cost_basis": None,
                   "manual_value": 30000, "reported_return_pct": None}],
                   "principal": None, "cash": None, "warnings": [], "source": "文字",
                   "extracted_at": "2026-10-29T00:00:00Z"}
        with patch.object(holdings, "preview_import", new=AsyncMock(return_value=preview)) as extract:
            result = asyncio.run(platform_mcp.prepare_holdings_import("owner-a", text="示例基金金额3万元"))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["missing_quantity"], 1)
        self.assertIn(result["draft_id"], result["review_url"])
        self.assertEqual(extract.await_args.args[0], "owner-a")
        self.assertEqual(holdings.get_import_draft("owner-a", result["draft_id"])["positions"][0]["name"], "示例基金")
        with self.assertRaises(HTTPException):
            holdings.get_import_draft("owner-b", result["draft_id"])
        self.assertEqual(holdings.get_portfolios("owner-a"), [])

    def test_research_capabilities_are_mcp_tools_with_tool_owned_validation(self) -> None:
        names = {item["function"]["name"] for item in platform_mcp.definitions()}
        self.assertIn("mcp__finch__research", names)
        self.assertIn("get_historical_cycles", platform_mcp.catalog()["research_tools"])
        with self.assertRaises(HTTPException) as missing:
            asyncio.run(platform_mcp.research("owner-a", "get_historical_cycles", {}))
        self.assertEqual(missing.exception.status_code, 422)
        self.assertIn("instrument_id", missing.exception.detail)

    def test_extension_install_requires_reauthentication_and_private_input(self) -> None:
        names = {item["function"]["name"] for item in platform_mcp.definitions()}
        self.assertIn("mcp__finch__manage_extension", names)
        with self.assertRaises(HTTPException) as unverified:
            asyncio.run(platform_mcp.manage_extension("owner-a", "install_mcp_config"))
        self.assertEqual(unverified.exception.status_code, 428)
        with self.assertRaises(HTTPException) as missing:
            asyncio.run(platform_mcp.manage_extension("owner-a", "install_mcp_config", reauth_valid=True))
        self.assertEqual(missing.exception.status_code, 422)

    def test_local_paper_resources_are_owner_bound(self) -> None:
        main.initialize()
        broker_a = platform_mcp._paper_broker("owner-a")
        broker_a.initialize()
        created = broker_a.create_account(paper.AccountRequest(label="测试模拟盘", market="US", initial_cash="10000"), "create-a")
        account_id = created["account_id"]
        with connect() as db:
            db.execute("INSERT INTO paper_orders(order_id,idempotency_key,account_id,instrument_id,side,order_type,quantity,limit_price,status,risk_result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("order-a", "private-key", account_id, "US:AAPL", "buy", "limit", 1, 100, "accepted", "{}", paper.now(), paper.now()))
        accounts = asyncio.run(platform_mcp.read("owner-a", "paper_local_accounts"))
        self.assertEqual(accounts[0]["account_id"], account_id)
        orders = asyncio.run(platform_mcp.read("owner-a", "paper_local_orders", {"account_id": account_id}))
        self.assertEqual(orders[0]["instrument_id"], "US:AAPL")
        self.assertNotIn("idempotency_key", orders[0])
        self.assertEqual(asyncio.run(platform_mcp.read("owner-b", "paper_local_accounts")), [])
        self.assertEqual(asyncio.run(platform_mcp.read("owner-b", "paper_local_orders")), [])
        with self.assertRaises(HTTPException) as denied:
            asyncio.run(platform_mcp.read("owner-b", "paper_local_accounts", {"account_id": account_id}))
        self.assertEqual(denied.exception.status_code, 404)

    def test_futu_resources_separate_modes_and_hide_order_credentials(self) -> None:
        account = {"id": "futu-real-us-opaque", "acc_id": "12345678", "market": "US", "mode": "REAL",
                   "label": "富途 US · 尾号 5678", "account_suffix": "5678", "currency": "USD"}
        row = {"order_id": "FT-1", "connection_id": account["id"], "body_json": json.dumps({
            "instrument_id": "US:AAPL", "side": "buy", "quantity": 1, "limit_price": "100"}),
            "notional": "100", "status": "filled", "broker_status": "FILLED_ALL",
            "filled_quantity": 1, "error": None, "created_at": "2026-10-27T00:00:00Z",
            "updated_at": "2026-10-27T00:01:00Z", "request_key": "secret-request"}
        with patch.object(platform_mcp.security, "primary_owner_id", return_value="owner-a"), \
             patch.object(futu_trade, "_discover", side_effect=lambda mode: ([account], []) if mode == "REAL" else ([], [])), \
             patch.object(futu_trade, "snapshot", return_value={"connection_id": account["id"], "cash": 100,
                                                                 "positions": [], "as_of": "2026-10-27T00:00:00Z", "source": "富途 OpenD"}), \
             patch.object(futu_trade, "_orders", return_value=[row]) as orders_call:
            real = asyncio.run(platform_mcp.read("owner-a", "live_futu_accounts"))
            self.assertEqual(len(real["accounts"]), 1)
            self.assertNotIn("acc_id", real["accounts"][0])
            self.assertEqual(asyncio.run(platform_mcp.read("owner-a", "paper_futu_accounts"))["accounts"], [])
            detail = asyncio.run(platform_mcp.read("owner-a", "live_futu_accounts", {"connection_id": account["id"]}))
            self.assertEqual(detail["cash"], 100)
            orders = asyncio.run(platform_mcp.read("owner-a", "live_futu_orders", {"connection_id": account["id"]}))
            self.assertEqual(orders["orders"][0]["status"], "filled")
            self.assertNotIn("request_key", orders["orders"][0])
            self.assertEqual(orders_call.call_args.args[0], "REAL")
            with self.assertRaises(HTTPException) as denied:
                asyncio.run(platform_mcp.read("owner-b", "live_futu_accounts"))
            self.assertEqual(denied.exception.status_code, 403)
        for resource in ("paper_local_accounts", "paper_futu_orders", "live_futu_accounts", "live_futu_orders"):
            self.assertIn(resource, platform_mcp.catalog()["readable"])
            self.assertNotIn(resource, platform_mcp.catalog()["writable"])


if __name__ == "__main__":
    unittest.main()
