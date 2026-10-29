"""Real holdings stay owner-scoped and never invent a valuation or profit."""

from __future__ import annotations

import os
import base64
import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import holdings, chat_images, ai_tools, main
from app.mysql_db import connect


class HoldingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.old_env = {key: os.environ.get(key) for key in ("DATA_DIR", "MYSQL_PASSWORD", "MYSQL_PASSWORD_FILE", "CONTAINER_RUNTIME")}
        os.environ["DATA_DIR"] = self.temporary.name
        os.environ["CONTAINER_RUNTIME"] = "false"
        os.environ.pop("MYSQL_PASSWORD", None)
        os.environ.pop("MYSQL_PASSWORD_FILE", None)
        with connect() as db:
            db.execute("CREATE TABLE quotes(instrument_id TEXT PRIMARY KEY,name TEXT,last REAL,currency TEXT,change_percent REAL,received_at TEXT,provider TEXT,freshness TEXT)")
        holdings.initialize()
        chat_images.initialize()

    def tearDown(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temporary.cleanup()

    def test_research_snapshot_requires_selected_owner_account(self) -> None:
        holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput(positions=[
            holdings.PositionInput(instrument_id="CN:600519", name="贵州茅台", asset_class="stock", quantity=2, cost_basis=3000),
        ]))
        account = main.research_account_snapshot("owner-a", "personal-CNY")
        self.assertEqual(account["positions"][0]["quantity"], 2)
        self.assertEqual(account["mode"], "personal")
        for owner, account_id in (("owner-b", "personal-CNY"), ("owner-a", "manual-other")):
            with self.assertRaises(HTTPException) as raised:
                main.research_account_snapshot(owner, account_id)
            self.assertEqual(raised.exception.status_code, 422)

    def test_authorized_research_tool_returns_real_position_evidence(self) -> None:
        holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput(positions=[
            holdings.PositionInput(instrument_id="FUND:510300", name="沪深300 ETF", asset_class="fund", quantity=10, cost_basis=50),
        ]))
        account = main.research_account_snapshot("owner-a", "personal-CNY")
        tools = ai_tools.ResearchTools(lambda _: {}, lambda _: None, lambda row: dict(row),
                                       lambda _: {}, lambda _: account, "personal-CNY")
        result = asyncio.run(tools.execute("get_account_snapshot", {"account_id": "personal-CNY"}))
        self.assertEqual(result["positions"][0]["name"], "沪深300 ETF")
        self.assertEqual(result["positions"][0]["quantity"], 10)
        self.assertEqual(result["evidence"][0]["type"], "account_snapshot")
        with self.assertRaises(ValueError):
            asyncio.run(tools.execute("get_account_snapshot", {"account_id": "personal-USD"}))

    def test_allocation_profit_and_owner_isolation(self) -> None:
        with connect() as db:
            for code, name, price, change in (("CN:600519", "贵州茅台", 200, 1.5), ("FUND:510300", "沪深300 ETF", 1.5, -0.4), ("GOLD:Au99.99", "黄金", 500, 0.2)):
                db.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)", (code, name, price, "CNY", change, "2026-10-27T01:00:00+00:00", "test quote", "fresh"))
        snapshot = holdings.SnapshotInput(principal=10000, cash=500, positions=[
            holdings.PositionInput(instrument_id="CN:600519", name="贵州茅台", asset_class="stock", quantity=10, cost_basis=1500),
            holdings.PositionInput(instrument_id="FUND:510300", name="沪深300 ETF", asset_class="fund", quantity=100, cost_basis=130),
            holdings.PositionInput(instrument_id="GOLD:Au99.99", name="黄金", asset_class="gold", quantity=20, cost_basis=9000),
        ])
        result = holdings.save_snapshot("owner-a", "CNY", snapshot)
        self.assertEqual(result["allocation"], {"stock": 2000.0, "fund": 150.0, "gold": 10000.0})
        self.assertEqual(result["total_assets"], 12650)
        self.assertEqual(result["total_pnl"], 2650)
        self.assertEqual(result["holdings_pnl"], 1520)
        self.assertEqual(result["holdings_return_pct"], 14.3)
        self.assertEqual(result["total_return_pct"], 26.5)
        self.assertEqual(next(item for item in result["positions"] if item["asset_class"] == "fund")["change_percent"], -0.4)
        self.assertEqual(holdings.get_portfolios("owner-b"), [])

    def test_missing_value_and_cost_remain_unknown(self) -> None:
        with self.assertRaisesRegex(Exception, "至少填写"):
            holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput())
        result = holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput(cash=100, positions=[
            holdings.PositionInput(instrument_id="CN:000001", name="平安银行", asset_class="stock", quantity=10),
        ]))
        self.assertIsNone(result["total_assets"])
        self.assertIsNone(result["holdings_pnl"])
        self.assertEqual(result["positions"][0]["valuation_source"], "missing")
        update = holdings.SnapshotInput(expected_updated_at=result["updated_at"], cash=100, positions=[
            holdings.PositionInput(instrument_id="CN:000001", name="平安银行", asset_class="stock", quantity=10, manual_value=120),
        ])
        revised = holdings.save_snapshot("owner-a", "CNY", update)
        self.assertEqual(revised["total_assets"], 220)
        self.assertIsNone(revised["holdings_pnl"])
        with self.assertRaisesRegex(Exception, "其他页面更新"):
            holdings.save_snapshot("owner-a", "CNY", update)

    def test_gold_fund_can_be_recorded_as_gold_in_cny(self) -> None:
        result = holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput(positions=[
            holdings.PositionInput(instrument_id="FUND:002963", name="易方达黄金ETF联接C", asset_class="gold", quantity=35686.30, cost_basis=114999.16, manual_value=97491.40, reported_return_pct=-15.22),
        ]))
        self.assertEqual(result["allocation"]["gold"], 97491.40)
        self.assertEqual(result["allocation"]["fund"], 0)
        self.assertEqual(result["positions"][0]["instrument_id"], "FUND:002963")
        self.assertEqual(result["positions"][0]["unrealized_pnl"], -17507.76)
        self.assertEqual(result["positions"][0]["reported_return_pct"], -15.22)

    def test_amount_only_text_position_uses_manual_value_without_inventing_shares(self) -> None:
        with connect() as db:
            db.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?)", ("FUND:018044", "示例基金", 1.8, "CNY", 0.1, "2026-10-29T01:00:00+00:00", "test quote", "fresh"))
        result = holdings.save_snapshot("owner-a", "CNY", holdings.SnapshotInput(positions=[
            holdings.PositionInput(instrument_id="FUND:018044", name="示例基金", asset_class="fund", manual_value=5162.81),
        ]))
        item = result["positions"][0]
        self.assertIsNone(item["quantity"])
        self.assertEqual(item["current_value"], 5162.81)
        self.assertEqual(item["valuation_source"], "manual")
        with self.assertRaisesRegex(HTTPException, "缺少份额和资料市值"):
            holdings.save_snapshot("owner-b", "CNY", holdings.SnapshotInput(positions=[
                holdings.PositionInput(instrument_id="FUND:018044", name="示例基金", asset_class="fund"),
            ]))

    def test_existing_sqlite_positions_migrate_to_optional_quantity(self) -> None:
        with connect() as db:
            db.execute("DROP TABLE personal_positions")
            db.execute("CREATE TABLE personal_positions (owner_id TEXT NOT NULL, currency TEXT NOT NULL, instrument_id TEXT NOT NULL, name TEXT NOT NULL, asset_class TEXT NOT NULL, quantity REAL NOT NULL, cost_basis REAL, manual_value REAL, updated_at TEXT NOT NULL, reported_return_pct REAL, PRIMARY KEY(owner_id,currency,instrument_id))")
            db.execute("INSERT INTO personal_positions VALUES(?,?,?,?,?,?,?,?,?,?)", ("owner-a", "CNY", "FUND:018044", "示例基金", "fund", 100, None, 500, "2026-10-29T00:00:00+00:00", None))
        holdings.initialize()
        with connect() as db:
            row = db.execute("SELECT quantity FROM personal_positions WHERE owner_id='owner-a'").fetchone()
            nullable = next(item for item in db.execute("PRAGMA table_info(personal_positions)") if item["name"] == "quantity")
        self.assertEqual(row["quantity"], 100)
        self.assertEqual(nullable["notnull"], 0)

    def test_api_uses_authenticated_owner(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        payload = {"principal": 1000, "cash": 1000, "positions": []}
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"):
            self.assertEqual(client.put("/api/v1/holdings/CNY", json=payload).status_code, 200)
            self.assertEqual(len(client.get("/api/v1/holdings").json()["portfolios"]), 1)
        with patch.object(holdings.security, "current_owner_id", return_value="owner-b"):
            self.assertEqual(client.get("/api/v1/holdings").json()["portfolios"], [])

    def test_screenshot_draft_keeps_reported_rate_separate_from_live_return(self) -> None:
        draft = holdings.parse_screenshot_preview('{"principal":1000,"cash":100,"positions":[{"instrument_id":"HK:700","name":"腾讯控股","asset_class":"stock","quantity":10,"cost_basis":800,"manual_value":900,"reported_return_pct":12.5}]}', "HKD")
        self.assertEqual(draft["positions"][0]["instrument_id"], "HK:00700")
        result = holdings.save_snapshot("owner-a", "HKD", holdings.SnapshotInput(principal=draft["principal"], cash=draft["cash"], positions=[holdings.PositionInput(**item) for item in draft["positions"]]))
        self.assertEqual(result["positions"][0]["reported_return_pct"], 12.5)
        self.assertEqual(result["positions"][0]["unrealized_return_pct"], 12.5)
        self.assertEqual(result["total_return_pct"], 0)

    def test_screenshot_preview_never_writes_without_review(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode()
        response = {"content": '{"positions":[{"instrument_id":"CN:600519","name":"贵州茅台","asset_class":"stock","quantity":2,"manual_value":3000,"reported_return_pct":5}],"warnings":[]}'}
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"), \
             patch.object(holdings, "load_model_configs", return_value=([SimpleNamespace(supports_vision=True)], None)), \
             patch.object(holdings, "_chat", new=AsyncMock(return_value=response)):
            result = client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "image_data_url": image})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["positions"][0]["reported_return_pct"], 5)
            self.assertEqual(holdings.get_portfolios("owner-a"), [])

    def test_screenshot_preview_uses_a_vision_capable_model(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode()
        text_model = SimpleNamespace(supports_vision=False)
        vision_model = SimpleNamespace(supports_vision=True)
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"), \
             patch.object(holdings, "load_model_configs", return_value=([text_model, vision_model], None)), \
             patch.object(holdings, "_chat", new=AsyncMock(return_value={"content": '{"cash":100,"positions":[]}'})) as chat:
            result = client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "image_data_url": image})
            self.assertEqual(result.status_code, 200)
            self.assertIs(chat.await_args.args[0], vision_model)

    def test_text_import_creates_review_draft_without_image_or_quantity(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        text_model = SimpleNamespace(supports_vision=False)
        response = {"content": '{"principal":null,"cash":null,"positions":[{"instrument_id":null,"name":"万家稳鑫","asset_class":"fund","quantity":null,"cost_basis":null,"manual_value":null},{"instrument_id":null,"name":"长信30天","asset_class":"fund","quantity":null,"cost_basis":null,"manual_value":null}],"warnings":["两只底仓合计约8万元，无法分配到单只持仓"]}'}
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"), \
             patch.object(holdings, "load_model_configs", return_value=([text_model], None)), \
             patch.object(holdings, "_chat", new=AsyncMock(return_value=response)) as chat:
            result = client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "text": "万家稳鑫3万，长信30天5万，合计8万；帮我导入持仓"})
            self.assertEqual(result.status_code, 200)
            draft = result.json()
            self.assertEqual(draft["source"], "文字")
            self.assertEqual(len(draft["positions"]), 2)
            self.assertIsNone(draft["positions"][0]["quantity"])
            self.assertIsNone(draft["positions"][0]["instrument_id"])
            self.assertTrue(any("补填" in warning for warning in draft["warnings"]))
            self.assertIs(chat.await_args.args[0], text_model)
            self.assertIsInstance(chat.await_args.args[1][1]["content"], str)
            self.assertEqual(holdings.get_portfolios("owner-a"), [])

    def test_text_import_rejects_ambiguous_sources(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"):
            self.assertEqual(client.post("/api/v1/holdings/import-preview", json={"currency": "CNY"}).status_code, 422)
            self.assertEqual(client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "text": "some holdings", "image_id": "image-a"}).status_code, 422)

    def test_gold_fund_without_visible_code_stays_in_review_draft(self) -> None:
        content = '{"principal":null,"cash":null,"positions":[{"instrument_id":null,"name":"易方达黄金ETF联接C","asset_class":"gold","quantity":35686.30,"cost_basis":null,"manual_value":97491.40,"reported_return_pct":-15.22}],"warnings":[]}'
        draft = holdings.parse_screenshot_preview(content, "CNY")
        self.assertEqual(len(draft["positions"]), 1)
        position = draft["positions"][0]
        self.assertIsNone(position["instrument_id"])
        self.assertEqual(position["asset_class"], "gold")
        self.assertEqual(position["quantity"], 35686.30)
        self.assertEqual(position["manual_value"], 97491.40)
        self.assertEqual(position["reported_return_pct"], -15.22)
        self.assertIsNone(position["cost_basis"])
        self.assertTrue(any("补填" in warning for warning in draft["warnings"]))
        self.assertEqual(holdings.get_portfolios("owner-a"), [])

    def test_saved_session_image_can_be_reused_for_import(self) -> None:
        app = FastAPI()
        app.include_router(holdings.router)
        client = TestClient(app)
        image = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nimage").decode()
        stored = chat_images.save("owner-a", "session-a", "黄金持仓.png", image)
        response = {"content": '{"positions":[{"instrument_id":null,"name":"易方达黄金ETF联接C","asset_class":"gold","quantity":35686.3,"manual_value":97491.4,"reported_return_pct":-15.22}]}'}
        with patch.object(holdings.security, "current_owner_id", return_value="owner-a"), \
             patch.object(holdings, "load_model_configs", return_value=([SimpleNamespace(supports_vision=True)], None)), \
             patch.object(holdings, "_chat", new=AsyncMock(return_value=response)):
            result = client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "image_id": stored["image_id"]})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["positions"][0]["name"], "易方达黄金ETF联接C")
            with patch.object(holdings.security, "current_owner_id", return_value="owner-b"):
                denied = client.post("/api/v1/holdings/import-preview", json={"currency": "CNY", "image_id": stored["image_id"]})
                self.assertEqual(denied.status_code, 404)


if __name__ == "__main__":
    unittest.main()
