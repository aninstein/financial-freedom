"""The broker substitute proves environment isolation and no replay after uncertainty."""
import asyncio

import pytest
from fastapi import HTTPException

from app import futu_trade


class Broker:
    def __init__(self):
        self.sent = []
        self.cancelled = []
        self.history_calls = 0
        self.fail_send = False

    def call(self, market, method, **kwargs):
        if method == "get_acc_list":
            return [
                {"acc_id": 11, "trd_env": "SIMULATE", "trdmarket_auth": "US", "security_firm": "FUTUSECURITIES"},
                {"acc_id": 22, "trd_env": "REAL", "trdmarket_auth": "US", "security_firm": "FUTUSECURITIES"},
            ]
        if method == "accinfo_query":
            return [{"cash": 100000, "total_assets": 100000}]
        if method == "position_list_query":
            return []
        if method == "acctradinginfo_query":
            return [{"max_cash_buy": 1000, "max_position_sell": 1000}]
        if method == "place_order":
            self.sent.append((market, kwargs.copy()))
            if self.fail_send:
                raise futu_trade.FutuError("timeout")
            return [{"order_id": 12345, "order_status": "SUBMITTED"}]
        if method == "order_list_query":
            if self.fail_send:
                return []
            return [{"order_id": 12345, "remark": self.sent[0][1]["remark"], "order_status": "FILLED_ALL", "dealt_qty": 1}]
        if method == "history_order_list_query":
            self.history_calls += 1
            return [{"order_id": 12345, "remark": self.sent[0][1]["remark"], "order_status": "FILLED_ALL", "dealt_qty": 1}]
        if method == "modify_order":
            self.cancelled.append((market, kwargs.copy()))
            return [{}]
        raise AssertionError(method)


def test_futu_environment_and_idempotency(monkeypatch, tmp_path):
    assert futu_trade.MARKETS["CN"] == "CNH"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("FUTU_TRADE_ENABLED", "true")
    monkeypatch.setenv("FUTU_REAL_ACCOUNT_IDS", "22")
    monkeypatch.setenv("FUTU_REAL_SYMBOLS", "US:AAPL")
    monkeypatch.setenv("FUTU_SIMULATE_ORDERS_ENABLED", "true")
    monkeypatch.setenv("FUTU_REAL_ORDERS_ENABLED", "false")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "false")
    monkeypatch.setattr(futu_trade.security, "current_owner_id", lambda: "owner")
    monkeypatch.setattr(futu_trade.security, "primary_owner_id", lambda: "owner")
    broker = Broker()
    monkeypatch.setattr(futu_trade, "CLIENT", broker)
    futu_trade.configure(lambda _: {"phase": "open"})
    futu_trade.initialize()

    async def scenario():
        paper = await futu_trade.accounts("SIMULATE")
        real = await futu_trade.accounts("REAL")
        assert len(paper) == len(real) == 1
        assert paper[0]["id"] != real[0]["id"]
        assert "-11" not in paper[0]["id"] and "-22" not in real[0]["id"]
        draft = futu_trade.Draft(connection_id=paper[0]["id"], instrument_id="US:AAPL", side="buy", quantity=1, limit_price="100")
        preview = await futu_trade._preview(draft, "SIMULATE")
        submitted = await futu_trade._submit(futu_trade.Confirmation(preview_id=preview["preview_id"], confirm="SIMULATE ORDER"), "key-one", "SIMULATE")
        again = await futu_trade._submit(futu_trade.Confirmation(preview_id=preview["preview_id"], confirm="SIMULATE ORDER"), "key-one", "SIMULATE")
        assert submitted["order_id"] == again["order_id"]
        assert len(broker.sent) == 1
        assert broker.sent[0][1]["trd_env"] == "SIMULATE"
        assert broker.sent[0][1]["acc_id"] == 11
        assert len(futu_trade._orders("REAL", "owner")) == 0
        resolved = await futu_trade._reconcile(paper[0]["id"], "SIMULATE")
        assert resolved["orders"][0]["status"] == "filled"
        assert resolved["orders"][0]["filled_quantity"] == 1

        real_draft = draft.model_copy(update={"connection_id": real[0]["id"]})
        read_only = await futu_trade._preview(real_draft, "REAL")
        assert read_only["trading_enabled"] is False
        with pytest.raises(HTTPException):
            await futu_trade._submit(futu_trade.Confirmation(preview_id=read_only["preview_id"], confirm="REAL ORDER"), "real-key", "REAL")
        assert len(broker.sent) == 1
        monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
        monkeypatch.setenv("FUTU_REAL_ORDERS_ENABLED", "true")
        ready = await futu_trade._preview(real_draft, "REAL")
        real_order = await futu_trade._submit(futu_trade.Confirmation(preview_id=ready["preview_id"], confirm="REAL ORDER"), "real-key", "REAL")
        assert real_order["status"] == "submitted"
        assert broker.sent[1][1]["trd_env"] == "REAL"
        assert broker.sent[1][1]["acc_id"] == 22
        assert len(futu_trade._orders("SIMULATE", "owner")) == 1
        canceled = await futu_trade._cancel(real_order["order_id"], "REAL")
        assert canceled["status"] == "cancel_requested"
        assert broker.cancelled[0][1]["trd_env"] == "REAL"

    asyncio.run(scenario())


def test_unknown_result_is_not_replayed(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MYSQL_PASSWORD", raising=False)
    monkeypatch.delenv("MYSQL_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("FUTU_TRADE_ENABLED", "true")
    monkeypatch.setenv("FUTU_SIMULATE_ORDERS_ENABLED", "true")
    monkeypatch.setattr(futu_trade.security, "current_owner_id", lambda: "owner")
    monkeypatch.setattr(futu_trade.security, "primary_owner_id", lambda: "owner")
    broker = Broker()
    broker.fail_send = True
    monkeypatch.setattr(futu_trade, "CLIENT", broker)
    futu_trade.configure(lambda _: {"phase": "open"})
    futu_trade.initialize()

    async def scenario():
        acc = (await futu_trade.accounts("SIMULATE"))[0]
        draft = futu_trade.Draft(connection_id=acc["id"], instrument_id="US:AAPL", side="buy", quantity=1, limit_price="100")
        preview = await futu_trade._preview(draft, "SIMULATE")
        confirm = futu_trade.Confirmation(preview_id=preview["preview_id"], confirm="SIMULATE ORDER")
        first = await futu_trade._submit(confirm, "uncertain", "SIMULATE")
        same = await futu_trade._submit(confirm, "uncertain", "SIMULATE")
        assert first["status"] == same["status"] == "unknown"
        assert len(broker.sent) == 1
        second = await futu_trade._preview(draft, "SIMULATE")
        with pytest.raises(HTTPException) as blocked:
            await futu_trade._submit(futu_trade.Confirmation(preview_id=second["preview_id"], confirm="SIMULATE ORDER"), "another", "SIMULATE")
        assert blocked.value.status_code == 409
        assert len(broker.sent) == 1
        resolved = await futu_trade._reconcile(acc["id"], "SIMULATE")
        assert broker.history_calls == 1
        assert resolved["orders"][0]["status"] == "filled"

    asyncio.run(scenario())
