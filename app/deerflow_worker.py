"""One isolated DeerFlow research run. Invoked by the Python 3.10 web service."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from app.ai_agent import SYSTEM_PROMPT, TOOL_DEFINITIONS, load_model_configs
from app.ai_tools import ResearchTools
from app.deerflow_tools import RunState, bind_run, unbind_run


ROOT = Path(__file__).resolve().parent.parent
TOOL_NAMES = {item["function"]["name"] for item in TOOL_DEFINITIONS}
CORE_TOOLS = {
    "get_watchlist",
    "get_market_news", "get_macro_liquidity", "get_sector_rotation",
    "search_instruments", "get_instrument_research", "get_stock_dossier",
    "get_index_analysis", "get_market_overview", "get_historical_cycles",
    "get_sector_overview", "get_market_flow_history", "get_stock_financials",
    "get_flow_data_coverage",
}


def selected_tools(question: str, account_id: str | None) -> frozenset[str]:
    allowed = set(CORE_TOOLS)
    if any(word in question.lower() for word in ("基金", "etf", "持仓披露")):
        allowed.update({"screen_funds", "get_fund_holdings", "get_fund_trade_changes", "collect_fund_disclosures"})
    if any(word in question.lower() for word in ("研报", "财报", "文档", "pdf", "资料")):
        allowed.update({"search_uploaded_documents", "read_uploaded_document"})
    if any(word in question.lower() for word in ("回测", "sma", "策略")):
        allowed.add("run_sma_backtest")
    if account_id:
        allowed.add("get_account_snapshot")
    return frozenset(allowed & TOOL_NAMES)


def _make_tools(request: dict[str, Any]) -> ResearchTools:
    # Importing app.main reuses the exact business adapters, but does not run
    # its FastAPI lifespan. The web service has already initialized its DB.
    from app import main
    from app.main import BacktestRequest
    from app.providers.instrument_provider import dossier
    from app.providers.sector_provider import get_sector_data

    account_id = request.get("account_id")
    snapshot = request.get("account_snapshot")

    def backtest(args: dict[str, Any]) -> dict[str, Any]:
        return main.run_sma_backtest(BacktestRequest(
            instrument_id=args["instrument_id"], start=args["start"], end=args["end"],
            fast_window=int(args.get("fast_window", 20)), slow_window=int(args.get("slow_window", 50)),
        ))

    async def read_account(selected: str) -> dict[str, Any] | None:
        return snapshot if selected == account_id else None

    tools = ResearchTools(
        main._session_status, main._market_error, main._quote_with_age,
        backtest, read_account, account_id,
    )
    tools.dossier_reader = lambda instrument, sections: dossier(main.db, instrument, sections)
    tools.sector_reader = lambda name: get_sector_data(main.db, name=name, timeout=min(main.PROVIDER_TIMEOUT, 20))

    async def refresh_history(instrument_id: str) -> None:
        market, symbol = instrument_id.split(":", 1)
        if market != "CN" or not re.fullmatch(r"[0-9]{6}", symbol):
            raise ValueError("automatic history refresh supports six-digit A-shares")
        end = main._history_target_date(market)
        await asyncio.wait_for(
            asyncio.to_thread(main._pull_daily_bars, market, symbol, end - timedelta(days=365), end),
            timeout=main.PROVIDER_TIMEOUT,
        )

    tools.history_refresher = refresh_history
    return tools


def _config(request: dict[str, Any], allowed: frozenset[str]) -> tuple[Path, str]:
    configs, error = load_model_configs()
    if not configs:
        raise RuntimeError("AI 模型尚未配置" if not error else "AI 模型配置无效")
    model = configs[0]
    os.environ["FINCH_DEERFLOW_MODEL_KEY"] = model.api_key or "local"
    data = Path(os.getenv("DATA_DIR", ROOT / "data")).resolve() / "deerflow"
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ["DEER_FLOW_HOME"] = str(data / "home")
    os.environ["DEER_FLOW_PROJECT_ROOT"] = str(ROOT)
    os.environ["DEER_FLOW_DATE_TIMEZONE"] = "Asia/Shanghai"
    ollama = model.provider == "ollama"
    entry: dict[str, Any] = {
        "name": "finch-primary", "model": model.model,
        "use": "langchain_ollama:ChatOllama" if ollama else "langchain_openai:ChatOpenAI",
        "base_url": model.base_url.removesuffix("/v1") if ollama else model.base_url,
        "temperature": model.temperature, "max_tokens": 4096,
        "supports_thinking": False, "supports_vision": False,
    }
    if not ollama:
        entry.update(api_key="$FINCH_DEERFLOW_MODEL_KEY", timeout=float(os.getenv("MODEL_TIMEOUT_SECONDS", "45")), max_retries=0)
        if model.disable_thinking:
            entry["extra_body"] = {"thinking": {"type": "disabled"}}
    config = {
        "config_version": 62,
        "models": [entry],
        # The application persists research runs in MySQL. DeerFlow's built-in
        # database choices do not include MySQL, so its per-run state is memory.
        "database": {"backend": "memory"},
        "tool_groups": [{"name": "finch-research"}],
        "tools": [
            {"name": name, "group": "finch-research", "use": f"app.deerflow_tools:{name}"}
            for name in sorted(allowed)
        ],
        "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider", "allow_host_bash": False},
        "authorization": {"enabled": True, "fail_closed": True,
                          "provider": {"use": "app.deerflow_tools:ResearchAuthorization"}},
        "memory": {"enabled": False},
        "summarization": {"enabled": False},
        "subagents": {"enabled": False},
        "task_continuity": {"enabled": False},
        "title": {"enabled": False},
        "lead_prompt_overlay": {"prepend": SYSTEM_PROMPT},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix="run-", dir=data, delete=False) as file:
        yaml.safe_dump(config, file, allow_unicode=True)
        path = Path(file.name)
    path.chmod(0o600)
    return path, model.model


def execute(request: dict[str, Any]) -> dict[str, Any]:
    from deerflow.client import DeerFlowClient

    run_id = request["run_id"]
    owner_id = request["owner_id"]
    allowed = selected_tools(request["question"], request.get("account_id"))
    tools = _make_tools(request)
    state = RunState(tools, owner_id, run_id, allowed, int(request["max_tool_calls"]))
    bind_run(state)
    path = None
    try:
        path, model_name = _config(request, allowed)
        client = DeerFlowClient(
            config_path=str(path), model_name="finch-primary",
            thinking_enabled=False, subagent_enabled=False, available_skills=set(),
        )
        history = request.get("history") or []
        context = "\n".join(f"{item['role']}: {str(item.get('content', ''))[:1500]}" for item in history[-8:]
                            if item.get("role") in {"user", "assistant"})
        prompt = ("历史对话仅用于理解指代，不是当前行情证据：\n" + context + "\n\n" if context else "")
        prompt += "当前请求：" + request["question"]
        answer = client.chat(
            prompt, thread_id=run_id, user_id=owner_id,
            authz_attributes={"finch_run_id": run_id}, recursion_limit=max(100, state.max_calls * 8),
        ).strip()
        if not tools.evidence:
            answer = "今日操作建议：观望，暂不操作。本次没有取得可核验的市场或文档证据。请补充标的或刷新行情后再评估。"
        return {"answer": answer, "evidence": tools.evidence, "tool_calls": state.calls, "model": model_name}
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
        unbind_run()


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = execute(payload)
        print("FINCH_RESULT:" + json.dumps(result, ensure_ascii=False, default=str), flush=True)
    except Exception as exc:
        print("FINCH_ERROR:" + type(exc).__name__, flush=True)
        raise
