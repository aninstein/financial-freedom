import { ensureRecentIdentity } from "./identity.js";
import { request } from "./api.js";
import { resolveInstrument, resolveInstrumentText } from "./instrument-search.js";
import {
  esc,
  icon,
  money,
  number,
  tone,
  time,
  empty,
  markdown,
  confirmDialog,
  showDialog,
  notify,
  stockHref,
} from "./ui.js";
let resetKey = null,
  resetDraft = null,
  paperMarkets = [];
let accountKey = null,
  aiKey = null,
  pollTimer = null,
  pollController = null;
const labels = {
  running: "研究与模拟交易中",
  complete: "本轮完成",
  failed: "运行失败",
  stopped: "已停止",
  interrupted: "已中断",
  accepted: "挂单中",
  filled: "模拟成交",
  cancelled: "已撤销",
  rejected: "风控拒绝",
};
const paperAccounts = (accounts) => accounts.filter((a) => a.mode === "paper");
const optionAccounts = (accounts, selected) =>
  paperAccounts(accounts)
    .map(
      (a) =>
        `<option value="${esc(a.account_id)}" ${selected === a.account_id ? "selected" : ""}>${esc(a.label)} · ${esc(a.market_name)} · ${esc(a.currency)}</option>`,
    )
    .join("");
const keyed = (old, body) =>
  old?.signature === JSON.stringify(body)
    ? old
    : { signature: JSON.stringify(body), key: crypto.randomUUID() };
export function cleanupPaper() {
  clearTimeout(pollTimer);
  pollController?.abort();
  pollController = null;
}
function tradingTabs(active, route) {
  const href = (tab) => {
    const params = new URLSearchParams(route.params);
    params.set("tab", tab);
    params.delete(tab === "orders" ? "account_page" : "page");
    return `#/trading?${params.toString()}`;
  };
  return `<nav class="paper-trading-tabs" aria-label="模拟交易功能"><a href="${href("accounts")}" ${active === "accounts" ? 'aria-current="page"' : ""}>账户与持仓</a><a href="${href("orders")}" ${active === "orders" ? 'aria-current="page"' : ""}>下单与订单</a></nav>`;
}
function orderEvidence(order) {
  let risk = {};
  try {
    risk = JSON.parse(order.risk_result || "{}");
  } catch {}
  return `<details><summary>风控与行情</summary><p>${esc(risk.reason || risk.execution_note || "本地模拟账本")}</p><p>来源：${esc(risk.quote_provider || "旧订单未记录")}</p><p>来源时点：${time(risk.quote_time || order.source_quote_at)}</p><p>状态：${esc(risk.freshness || "未知")}；${esc(risk.contract?.source || "基础数量规则")}</p>${risk.contract?.lot_size ? `<p>数量规则：${risk.contract.lot_size} 股${risk.contract.source_kind === "manual" ? "（手工模拟单位）" : ""}</p>` : ""}</details>`;
}
function ordersTable(rows, accounts, cancel = true) {
  if (!rows.length)
    return empty(
      "暂无模拟订单",
      "手动提交，或授权 AI 在明确范围内执行一轮。",
      "",
      "orders",
    );
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>标的 / 账户</th><th>方向 / 股数</th><th>成交价 / 限价</th><th>状态 / 来源</th><th>操作</th></tr></thead><tbody>${rows.map((o) => `<tr><td><a class="stock-link" href="${stockHref(o.instrument_id)}">${esc(o.instrument_id)}</a><small>${esc(accounts.find((a) => a.account_id === o.account_id)?.label || o.account_id)}</small><small>${esc(o.order_id)}</small></td><td>${o.side === "buy" ? "买入" : "卖出"} ${number(o.quantity, 0)}<small>费用 ${number(o.fee)}</small></td><td class="mono">${o.fill_price == null ? "—" : number(o.fill_price, 4)}<small>限价 ${o.limit_price == null ? "—" : number(o.limit_price, 4)}</small></td><td><span class="tag ${o.status === "rejected" ? "amber" : ""}">${labels[o.status] || esc(o.status)}</span><small>${o.actor === "ai" ? "AI · " + esc(o.ai_run_id) : "手动委托"}</small>${o.reason ? `<details><summary>交易理由</summary><p>${esc(o.reason)}</p></details>` : ""}<small>${time(o.updated_at)}</small>${orderEvidence(o)}</td><td>${cancel && o.status === "accepted" ? `<button class="button small" data-action="cancel-order" data-id="${esc(o.order_id)}">撤单</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>`;
}
function runRows(runs) {
  return runs.length
    ? `<div class="paper-run-list">${runs.map((r) => `<article class="provider-item"><div class="paper-run-head"><strong>${esc(r.run_id)}</strong><span class="tag ${r.status === "running" ? "accent" : ""}">${labels[r.status] || esc(r.status)}</span></div><p>${esc(r.mandate.objective.slice(0, 160))}</p><p>${esc(r.mandate.instruments.join(" · "))} · ${r.orders.length}/${r.mandate.max_orders} 笔委托 · ${time(r.created_at)}</p>${r.error ? `<p class="form-error">${esc(r.error)}</p>` : ""}<div class="actions section-gap"><button class="button small" data-action="paper-run-detail" data-id="${esc(r.run_id)}">研究与订单详情</button>${r.status === "running" || r.orders.some((o) => o.status === "accepted") ? `<button class="button small danger" data-action="paper-stop" data-id="${esc(r.run_id)}">${r.status === "running" ? "停止并撤销挂单" : "撤销本轮挂单"}</button>` : ""}</div></article>`).join("")}</div>`
    : empty(
        "还没有 AI 模拟交易记录",
        "指定账户和股票范围，授权后开始一轮有边界的研究与交易。",
        "",
        "spark",
      );
}
function pollRuns(signal, account) {
  clearTimeout(pollTimer);
  const next = async () => {
    if (signal.aborted) return;
    try {
      const runs = await request(
        "/paper/ai/runs" +
          (account ? "?account_id=" + encodeURIComponent(account) : ""),
        { signal },
      );
      if (signal.aborted) return;
      const target = document.querySelector("#paper-runs");
      if (target) target.innerHTML = runRows(runs);
      if (runs.some((r) => r.status === "running"))
        pollTimer = setTimeout(next, 5000);
    } catch (e) {
      if (!signal.aborted) {
        const target = document.querySelector("#paper-runs-status");
        if (target)
          target.textContent = "状态刷新未完成，可点击刷新重试：" + e.message;
      }
    }
  };
  pollTimer = setTimeout(next, 5000);
}
export async function renderPaperAccounts(r, signal, ui) {
  const [accounts, markets, runs] = await Promise.all([
    request("/accounts", { signal }),
    request("/paper/markets", { signal }),
    request("/paper/ai/runs", { signal }),
  ]);
  if (signal.aborted) return;
  ui.setAccounts(accounts);
  paperMarkets = markets;
  const selected =
    r.params.get("account") ||
    r.params.get("ai") ||
    paperAccounts(accounts)[0]?.account_id;
  const current = accounts.find(
    (a) => a.account_id === selected && a.mode === "paper",
  );
  const allPaper = paperAccounts(accounts);
  const count = Math.max(1, Math.ceil(allPaper.length / 6));
  const cardPage = Math.min(
    count,
    Math.max(1, parseInt(r.params.get("account_page"), 10) || 1),
  );
  const cardLink = (n) => {
    const params = new URLSearchParams(r.params);
    params.set("account_page", n);
    return "#/accounts?" + params.toString();
  };
  const cards = allPaper
    .slice((cardPage - 1) * 6, cardPage * 6)
    .map(
      (a) =>
        `<section class="panel paper-account ${a.account_id === selected ? "is-selected" : ""}"><div class="panel-header"><div><h2>${esc(a.label)}</h2><p>${esc(a.market_name)} · ${esc(a.currency)}</p></div><span class="tag amber">模拟</span></div><div class="panel-body"><div class="paper-balance">${money(a.equity, a.currency)}</div><p class="field-help">总资产${a.valuation_complete ? "（持仓按缓存报价估值）" : "（部分持仓缺报价）"}</p><dl class="paper-account-metrics"><dt>初始资金</dt><dd>${money(a.initial_cash, a.currency)}</dd><dt>可用现金</dt><dd>${money(a.available_cash, a.currency)}</dd><dt>冻结现金</dt><dd>${money(a.frozen_cash, a.currency)}</dd><dt>已实现盈亏</dt><dd class="${tone(a.realized_pnl)}">${money(a.realized_pnl, a.currency)}</dd><dt>浮动盈亏</dt><dd class="${tone(a.unrealized_pnl)}">${money(a.unrealized_pnl, a.currency)}</dd></dl><div class="actions section-gap"><a class="button small" href="#/accounts?account=${encodeURIComponent(a.account_id)}">持仓与 AI</a><a class="button small primary" href="#/orders?account=${encodeURIComponent(a.account_id)}">模拟交易</a><button class="button small ghost" data-action="paper-reset-one" data-id="${esc(a.account_id)}">清零重开</button></div></div></section>`,
    )
    .join("");
  const positionRows = current?.positions.length
    ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>持仓</th><th>数量 / 可卖</th><th>平均成本</th><th>市值 / 浮盈亏</th><th>估值来源</th></tr></thead><tbody>${current.positions.map((p) => `<tr><td><a class="stock-link" href="${stockHref(p.instrument_id)}">${esc(p.name)}</a><small>${esc(p.instrument_id)}</small></td><td>${number(p.quantity, 0)} / ${number(p.sellable, 0)}<small>挂单占用 ${number(p.frozen, 0)}</small></td><td>${number(p.average_cost, 4)}</td><td>${money(p.market_value, current.currency)}<small class="${tone(p.unrealized_pnl)}">${money(p.unrealized_pnl, current.currency)}</small></td><td>${esc(p.provider || "暂无报价")}<small>${time(p.quote_time)} · ${esc(p.freshness)}</small></td></tr>`).join("")}</tbody></table></div>`
    : empty("暂无持仓", "成交后这里显示成本、可卖数量与估值来源。");
  ui.setPage(
    ui.page(
      ui.heading(
        "模拟交易",
        "独立资金、独立持仓。为每个市场创建实验账户，让 AI 在你指定的范围内实践。",
        `<button class="button" data-action="retry-route">${icon("refresh")}刷新余额</button><button class="button danger" data-action="paper-reset-all">全部模拟盘清零重开</button>`,
      ) +
        tradingTabs("accounts", r) +
        `<div class="actions field-help">共 ${allPaper.length} 个模拟盘 · 第 ${cardPage}/${count} 页 ${cardPage > 1 ? `<a class="button small" href="${cardLink(cardPage - 1)}">上一页</a>` : ""}${cardPage < count ? `<a class="button small" href="${cardLink(cardPage + 1)}">下一页</a>` : ""}</div><div class="paper-account-grid section-gap">${cards || empty("还没有模拟盘", "在下方创建一次独立实验并填写初始资金。")}</div><div class="section-gap split">${ui.panel("开通模拟盘", `<form class="panel-body" id="paper-account-form" novalidate data-draft><div class="form-row"><label class="field-label" for="paper-label">账户名称</label><input class="field" id="paper-label" name="label" maxlength="80" placeholder="例如 创业板趋势实验" /></div><div class="form-row"><label class="field-label" for="paper-market">市场 / 板块</label><select class="field" id="paper-market" name="market">${markets.map((m) => `<option value="${esc(m.market)}">${esc(m.name)} · ${esc(m.currency)}</option>`).join("")}</select><p class="field-help" id="paper-market-rule">${esc(markets[0]?.rule)}</p></div><div class="form-row"><label class="field-label" for="paper-initial">初始虚拟资金</label><input class="field" id="paper-initial" name="initial_cash" type="number" min="0.01" max="1000000000" step="0.01" placeholder="输入这次实验的初始资金"/><p class="field-help">币种随市场确定。开户后资金不自动重置；可建立多个独立实验账户。</p></div><div id="paper-account-error" class="form-error" role="alert"></div><button class="button primary" type="submit">创建模拟盘</button></form>`)}${ui.panel("持仓明细", `<div class="panel-body"><label class="field-label" for="paper-position-account">查看账户</label><select class="field" id="paper-position-account">${optionAccounts(accounts, selected)}</select><p class="field-help section-gap">A股当天买入不能当天卖出；可卖数量已扣除卖出挂单。估值使用缓存报价，需同时查看来源和时点。</p></div>${positionRows}`)}</div>` +
        `<section class="panel section-gap"><div class="panel-header"><div><h2>AI 模拟交易</h2><p>一次授权，一轮执行；可研究、不交易，也可在范围内自主下单。</p></div><span class="tag accent">仅本地模拟盘</span></div><form class="panel-body" id="paper-ai-form" novalidate data-draft><div class="form-grid"><div class="form-row"><label class="field-label" for="paper-ai-account">授权账户</label><select class="field" id="paper-ai-account" name="account_id">${optionAccounts(accounts, selected)}</select></div><div class="form-row"><label class="field-label" for="paper-ai-instruments">股票白名单（最多10只）</label><input class="field" id="paper-ai-instruments" name="instruments" placeholder="贵州茅台, CN:002594（多个标的用逗号分隔）" maxlength="320" /></div><div class="form-row"><label class="field-label" for="paper-ai-budget">本轮委托名义金额上限（账户原币种）</label><input class="field" id="paper-ai-budget" name="max_notional" type="number" min="0.01" step="0.01" value="10000" /></div><div class="form-row"><label class="field-label" for="paper-ai-count">最多委托笔数</label><input class="field" id="paper-ai-count" name="max_orders" type="number" min="1" max="5" value="3" /></div></div><div class="form-row"><label class="field-label" for="paper-ai-objective">研究与交易目标</label><textarea class="field resize-none" id="paper-ai-objective" name="objective" rows="3" maxlength="2000" placeholder="分析白名单股票的趋势与风险；有充分依据时小仓位模拟买入，不满足条件则不交易。"></textarea></div><label class="check-row"><input type="checkbox" name="authorize" id="paper-ai-authorize"/>授权 AI 本轮读取所选模拟账户并自主提交模拟订单</label><p class="field-help section-gap">账户现金、持仓、股票范围和目标将发送给当前配置的主模型。本轮委托名义额度在提交时占用，撤单不退回；新任务需重新授权。普通投研对话仍只读。</p><div class="form-error" id="paper-ai-error" role="alert"></div><button class="button primary" type="submit">${icon("spark")}授权并运行一轮</button></form></section>` +
        `<div class="section-gap">${ui.panel("最近20轮 AI 记录", `<div class="panel-body"><div id="paper-runs">${runRows(runs)}</div><p class="field-help" id="paper-runs-status" role="status">运行期间每5秒更新任务状态。已提交订单始终以账本记录为准。</p><button class="button small section-gap" data-action="paper-refresh-runs">刷新任务</button></div>`)}</div>` +
        `<p class="field-help section-gap">${markets.map((m) => `${esc(m.name)}：${esc(m.rule)}`).join("；")}。初始余额是虚拟资金；费用统一10bp，未完整模拟交易所税费、滑点、排队和公司行为。</p>` +
        `<details class="section-gap"><summary>外部账户快照（${accounts.filter((a) => a.mode !== "paper" && a.mode !== "live").length}）</summary><div class="paper-account-grid section-gap">${accounts
          .filter((a) => a.mode !== "paper" && a.mode !== "live")
          .map((a) =>
            ui.panel(
              a.label,
              `<div class="panel-body"><span class="tag">手工快照 · ${esc(a.currency)}</span><p class="paper-balance section-gap">${money(a.cash, a.currency)}</p><p class="field-help">${time(a.as_of)} · ${a.positions.length} 项持仓</p>${a.positions.map((p) => `<p><a class="text-link" href="${stockHref(p.instrument_id)}">${esc(p.instrument_id)}</a> · ${number(p.quantity)} 股 / 份</p>`).join("")}</div>`,
            ),
          )
          .join("")}</div></details>` +
        ui.manualSnapshot(accounts),
    ),
  );
  document.querySelector("#paper-market-rule").textContent =
    markets.find(
      (m) => m.market === document.querySelector("#paper-market").value,
    )?.rule || "";
  document.querySelector("#paper-market").onchange = (e) => {
    const m = markets.find((m) => m.market === e.target.value);
    document.querySelector("#paper-market-rule").textContent = m.rule;
  };
  document.querySelector("#paper-position-account").onchange = (e) =>
    (location.hash = "/accounts?account=" + encodeURIComponent(e.target.value));
  if (runs.some((r) => r.status === "running")) pollRuns(signal);
}

export async function renderPaperOrders(r, signal, ui) {
  const account = r.params.get("account") || "",
    p = Math.max(1, parseInt(r.params.get("page"), 10) || 1);
  const [accounts, rows] = await Promise.all([
    request("/accounts", { signal }),
    request(
      `/paper/orders?limit=21&offset=${(p - 1) * 20}${account ? "&account_id=" + encodeURIComponent(account) : ""}`,
      { signal },
    ),
  ]);
  if (signal.aborted) return;
  ui.setAccounts(accounts);
  const instrument = (r.params.get("instrument") || "").toUpperCase();
  const inferred = instrument.startsWith("US:")
    ? "US"
    : instrument.startsWith("HK:")
      ? "HK"
      : instrument.startsWith("CN:688")
        ? "CN_STAR"
        : /^CN:30[01]/.test(instrument)
          ? "CN_CHINEXT"
          : "CN_MAIN";
  const active =
    accounts.find((a) => a.account_id === account && a.mode === "paper") ||
    paperAccounts(accounts).find((a) => a.market === inferred) ||
    paperAccounts(accounts)[0];
  const filtered = rows.slice(0, 20);
  const link = (n) =>
    `#/orders?page=${n}${account ? "&account=" + encodeURIComponent(account) : ""}`;
  ui.setPage(
    ui.page(
      ui.heading(
        "模拟交易",
        "预览、确认、撮合；手动与 AI 委托共用同一风控和账本。",
        "",
      ) +
        tradingTabs("orders", r) +
        `<div class="split">${ui.panel("创建模拟订单", `<form class="panel-body" id="order-form" novalidate data-draft><div class="form-row"><label class="field-label" for="order-account">模拟账户</label><select class="field" id="order-account" name="account_id">${optionAccounts(accounts, active?.account_id)}</select></div><div class="form-row"><label class="field-label" for="order-instrument">股票名称或代码</label><span class="instrument-search"><input class="field" id="order-instrument" name="instrument_id" value="${esc(r.params.get("instrument") || "")}" placeholder="输入名称或代码，例如 比亚迪 / CN:002594" autocomplete="off" data-instrument-picker="select" role="combobox" aria-autocomplete="list" aria-controls="order-instrument-results" aria-expanded="false" /><span class="instrument-results" id="order-instrument-results" role="listbox" hidden></span></span></div><div class="form-grid"><div class="form-row"><label class="field-label" for="order-side">方向</label><select class="field" id="order-side" name="side"><option value="buy">买入</option><option value="sell">卖出</option></select></div><div class="form-row"><label class="field-label" for="order-type">类型</label><select class="field" id="order-type" name="type"><option value="market">市价</option><option value="limit">限价挂单</option></select></div><div class="form-row"><label class="field-label" for="order-quantity">股数</label><input class="field" id="order-quantity" name="quantity" type="number" min="1" step="1" value="${active?.market === "US" ? 1 : active?.market === "CN_STAR" ? 200 : 100}"/></div><div class="form-row" id="limit-row" hidden><label class="field-label" for="order-limit">限价</label><input class="field" id="order-limit" name="limit_price" type="number" min="0.0001" step="0.0001"/></div></div><p class="field-help">市价单仅在连续交易时段有新鲜、带来源时点的报价时成交。无行情/休市可挂限价单，冻结资金或持仓后等待。港股请先同步或确认下方买卖单位。</p><div class="form-error" id="order-error" role="alert"></div><div class="actions"><button class="button primary" type="submit">预览模拟订单</button><button class="button" type="button" data-action="paper-pull-quote">拉取该股报价</button></div><p class="field-help section-gap" id="order-receipt">${esc(ui.lastReceipt || "")}</p></form>`)}${ui.panel("订单记录", `<div class="panel-body"><label class="field-label" for="paper-order-filter">账户筛选</label><select class="field" id="paper-order-filter"><option value="">所有模拟账户</option>${optionAccounts(accounts, account)}</select></div>${ordersTable(filtered, accounts)}<div class="table-footnote actions">${p > 1 ? `<a class="button small" href="${link(p - 1)}">上一页</a>` : ""}<span>第 ${p} 页 · 每页20条</span>${rows.length > 20 ? `<a class="button small" href="${link(p + 1)}">下一页</a>` : ""}</div>`)}</div>` +
        `<section class="panel section-gap"><div class="panel-header"><div><h2>港股买卖单位</h2><p>每只证券各有每手股数，不统一按100股处理。</p></div><button class="button small" data-action="paper-sync-hk">同步港交所清单</button></div><div class="panel-body"><p id="paper-contract-status" class="field-help" role="status"></p><form id="paper-contract-form" novalidate data-draft><div class="form-grid"><div class="form-row"><label class="field-label" for="paper-contract-id">港股代码</label><input class="field" id="paper-contract-id" name="instrument_id" placeholder="HK:00700"/></div><div class="form-row"><label class="field-label" for="paper-contract-lot">模拟每手股数</label><input class="field" id="paper-contract-lot" name="lot_size" type="number" min="1" max="100000" step="1"/></div></div><div class="form-row"><label class="field-label" for="paper-contract-note">确认依据</label><input class="field" id="paper-contract-note" name="note" maxlength="160" placeholder="记录核对来源，或明确这是自定义模拟单位"/></div><p class="field-help">官方清单不可用时可手动录入，系统会标记为“用户确认的模拟规则”，7天内有效；AI不能改此规则。有挂单时须先撤单。</p><div id="paper-contract-error" class="form-error" role="alert"></div><button class="button" type="submit">确认模拟单位</button><button class="button ghost" type="button" data-action="paper-view-contract">查看当前规则</button></form></div></section><p class="field-help section-gap">报价快照全额模拟成交，费用10bp；不模拟盘口优先级、滑点、部分成交、完整税费或公司行为。挂单会持续等待至成交、撤销或拒绝，不是交易所当日有效委托。</p>`,
    ),
  );
  document.querySelector("#order-type").onchange = (e) =>
    (document.querySelector("#limit-row").hidden = e.target.value !== "limit");
  document.querySelector("#paper-order-filter").onchange = (e) =>
    (location.hash =
      "/orders" +
      (e.target.value ? "?account=" + encodeURIComponent(e.target.value) : ""));
}

export async function handlePaperSubmit(form, values, ui) {
  if (
    ![
      "paper-account-form",
      "paper-ai-form",
      "paper-contract-form",
      "paper-reset-form",
    ].includes(form.id)
  )
    return false;
  const errorId = {
    "paper-account-form": "paper-account-error",
    "paper-ai-form": "paper-ai-error",
    "paper-contract-form": "paper-contract-error",
    "paper-reset-form": "paper-reset-error",
  }[form.id];
  await ui.busy(form, async () => {
    try {
      if (form.id === "paper-reset-form") {
        if (values.typed_confirm !== "清零")
          throw new Error("请输入“清零”确认删除模拟交易数据");
        const body = {
          label: values.label.trim(),
          market: values.market,
          initial_cash: values.initial_cash,
          confirm: values.target
            ? "RESET PAPER ACCOUNT"
            : "RESET ALL PAPER ACCOUNTS",
        };
        if (!body.label || !(Number(body.initial_cash) > 0))
          throw new Error("请填写新模拟盘名称及初始资金");
        resetDraft = { ...values };
        resetKey = keyed(resetKey, { target: values.target, ...body });
        const path = values.target
          ? "/paper/accounts/" + encodeURIComponent(values.target) + "/reset"
          : "/paper/accounts/reset-all";
        const result = await request(path, {
          method: "POST",
          body,
          headers: { "Idempotency-Key": resetKey.key },
        });
        resetKey = null;
        resetDraft = null;
        document.querySelector("#app-dialog").close();
        ui.clearDraft(form);
        notify(
          `已清零 ${result.retired_accounts} 个模拟盘，创建新的独立模拟账户`,
        );
        location.hash =
          "/accounts?account=" + encodeURIComponent(result.account.account_id);
      } else if (form.id === "paper-account-form") {
        const body = {
          label: values.label.trim(),
          market: values.market,
          initial_cash: values.initial_cash,
        };
        if (!body.label || !(Number(body.initial_cash) > 0))
          throw new Error("请填写账户名称和大于零的初始虚拟资金");
        const yes = await confirmDialog(
          "创建这个模拟盘",
          `<p>${esc(body.label)} · ${esc(body.market)}</p><p>初始虚拟资金 ${esc(body.initial_cash)}，币种按市场确定；账户创建后不会自动重置。</p>`,
          "创建模拟盘",
        );
        if (!yes) return;
        accountKey = keyed(accountKey, body);
        const a = await request("/paper/accounts", {
          method: "POST",
          body,
          headers: { "Idempotency-Key": accountKey.key },
        });
        accountKey = null;
        ui.clearDraft(form);
        notify("模拟盘已创建");
        location.hash = "/accounts?account=" + encodeURIComponent(a.account_id);
      } else if (form.id === "paper-ai-form") {
        if (!values.authorize) throw new Error("请勾选本轮模拟交易授权");
        const tokens = values.instruments.split(/[,，\s]+/).filter(Boolean);
        const instruments = [];
        for (const token of tokens) {
          try {
            instruments.push(await resolveInstrumentText(token));
          } catch (error) {
            throw new Error(`${token}：${error.message}；同名标的请填写市场:代码`);
          }
        }
        const body = {
          account_id: values.account_id,
          instruments: [...new Set(instruments)],
          objective: values.objective.trim(),
          max_notional: values.max_notional,
          max_orders: Number(values.max_orders),
          authorize: true,
        };
        if (
          !body.instruments.length ||
          body.objective.length < 5 ||
          !(Number(body.max_notional) > 0)
        )
          throw new Error("请填写股票白名单、至少5个字的目标和有效金额上限");
        const yes = await confirmDialog(
          "授权 AI 执行本轮模拟交易",
          `<p>账户：${esc(ui.accounts().find((a) => a.account_id === body.account_id)?.label || body.account_id)}</p><p>范围：${esc(body.instruments.join("、"))}</p><p>最多 ${number(body.max_orders, 0)} 笔，委托名义金额上限 ${esc(body.max_notional)}（原币种）。AI可在此范围内自主买卖本地模拟持仓；账户摘要将发送给当前主模型。</p><p>已成交订单不能由停止按钮回滚；停止会阻止后续操作并撤销本轮挂单。</p>`,
          "授权并启动",
        );
        if (!yes) return;
        aiKey = keyed(aiKey, body);
        const run = await request("/paper/ai/runs", {
          method: "POST",
          body,
          headers: { "Idempotency-Key": aiKey.key },
        });
        aiKey = null;
        ui.clearDraft(form);
        notify("AI模拟交易任务已启动：" + run.run_id);
        ui.renderRoute();
      } else {
        const instrument = values.instrument_id.trim().toUpperCase();
        const body = {
          lot_size: Number(values.lot_size),
          note: values.note.trim(),
        };
        if (
          !Number.isInteger(body.lot_size) ||
          body.lot_size < 1 ||
          body.note.length < 3
        )
          throw new Error("请输入整数每手股数和至少3个字的确认依据");
        const yes = await confirmDialog(
          "确认港股模拟买卖单位",
          `<p>${esc(instrument)} · 每手 ${body.lot_size} 股</p><p>此规则标记为手工模拟规则，不代表官方已确认数据。这项手工规则仅影响你的模拟盘，官方清单不会自动覆盖你的选择。</p>`,
          "确认模拟规则",
        );
        if (!yes) return;
        const d = await request(
          "/paper/contracts/" + encodeURIComponent(instrument),
          { method: "PUT", body },
        );
        document.querySelector("#paper-contract-status").textContent =
          `${d.instrument_id} 每手${d.lot_size}股 · ${d.source} · ${time(d.updated_at)}`;
        notify("模拟买卖单位已保存");
      }
    } catch (e) {
      ui.formError(errorId, e.message, form.querySelector("input,textarea"));
      if (!form.isConnected) notify(e.message);
    }
  });
  return true;
}
export async function handlePaperAction(button, ui) {
  const action = button.dataset.action;
  if (!action?.startsWith("paper-")) return false;
  button.disabled = true;
  try {
    if (action === "paper-reset-one" || action === "paper-reset-all") {
      if (!(await ensureRecentIdentity())) return true;
      const target = action === "paper-reset-one" ? button.dataset.id : "";
      const account = ui.accounts().find((a) => a.account_id === target);
      const draft = resetDraft?.target === target ? resetDraft : null;
      showDialog(
        target ? "清零这个模拟盘并重新开始" : "全部模拟盘清零并重新开始",
        `<div class="alert error"><strong>${target ? "仅清理 " + esc(account?.label || target) : "清理当前登录用户的全部模拟盘"}</strong><p>将永久清除范围内的模拟订单、成交和AI交易记录，并停止相关AI任务。此操作不能撤销。随后按你指定的资金创建一个全新的模拟账户；真实账户和其他用户的数据不受影响。</p></div><form id="paper-reset-form" novalidate class="section-gap"><input type="hidden" name="target" value="${esc(target)}"/><div class="form-row"><label class="field-label" for="reset-label">新模拟盘名称</label><input class="field" id="reset-label" name="label" maxlength="80" value="${esc(draft?.label || account?.label || "新一轮模拟盘")}"/></div><div class="form-row"><label class="field-label" for="reset-market">市场</label><select class="field" id="reset-market" name="market">${paperMarkets.map((m) => `<option value="${esc(m.market)}" ${(draft?.market || (account?.market === "CN_ALL" ? "CN_MAIN" : account?.market)) === m.market ? "selected" : ""}>${esc(m.name)} · ${esc(m.currency)}</option>`).join("")}</select></div><div class="form-row"><label class="field-label" for="reset-cash">新模拟盘初始资金（所选市场原币种）</label><input class="field" id="reset-cash" name="initial_cash" type="number" min="0.01" max="1000000000" step="0.01" value="${esc(draft?.initial_cash || "")}" placeholder="由你指定新一轮的虚拟资金"/></div><div class="form-row"><label class="field-label" for="reset-confirm">输入“清零”确认</label><input class="field" id="reset-confirm" name="typed_confirm" autocomplete="off"/></div><div class="form-error" id="paper-reset-error" role="alert"></div><div class="actions"><button class="button" type="button" data-action="close-dialog">返回</button><button class="button danger" type="submit">清零并创建新模拟盘</button></div></form>`,
      );
    } else if (action === "paper-pull-quote") {
      const id = await resolveInstrument(document.querySelector("#order-instrument"));
      const d = await request("/paper/quotes/pull", {
        method: "POST",
        body: { instrument_id: id },
        timeout: 45000,
      });
      document.querySelector("#order-receipt").textContent =
        `${d.instrument_id} · ${money(d.last, d.currency)} · ${d.provider} · ${time(d.exchange_time)} · ${d.executable ? "当前满足模拟撮合时点要求" : "当前不满足撮合要求，可挂限价单"}`;
      notify("已接收来源报价");
    } else if (action === "paper-sync-hk") {
      const status = document.querySelector("#paper-contract-status");
      status.textContent = "正在请求港交所官方证券清单…";
      const d = await request("/paper/contracts/sync-hk", {
        method: "POST",
        timeout: 45000,
      });
      status.textContent = `已同步 ${d.count} 只港币股票 · ${time(d.updated_at)}`;
      notify("港股每手股数已同步");
    } else if (action === "paper-view-contract") {
      const id = document
        .querySelector("#paper-contract-id")
        .value.trim()
        .toUpperCase();
      const d = await request("/paper/contracts/" + encodeURIComponent(id));
      document.querySelector("#paper-contract-status").textContent =
        `${d.instrument_id} 每手 ${d.lot_size} 股 · ${d.source} · ${time(d.updated_at)}`;
    } else if (action === "paper-run-detail") {
      const d = await request(
        "/paper/ai/runs/" + encodeURIComponent(button.dataset.id),
      );
      showDialog(
        "AI模拟交易记录",
        `<span class="tag">${labels[d.status] || esc(d.status)}</span><p class="field-help section-gap">${esc(d.run_id)} · ${esc(d.model || "主模型")} · ${time(d.created_at)}</p><p class="section-gap">目标：${esc(d.mandate.objective)}</p>${d.error ? `<div class="alert error section-gap">${esc(d.error)}</div>` : ""}<div class="message-content section-gap">${markdown(d.answer || "尚无总结，以以下实际订单为准。")}</div><h3 class="section-gap">实际模拟订单（${d.orders.length}）</h3>${ordersTable(d.orders, ui.accounts(), false)}<details class="section-gap"><summary>工具证据（${d.evidence.length}）</summary><pre class="code-data">${esc(JSON.stringify(d.evidence, null, 2))}</pre></details>`,
      );
    } else if (action === "paper-stop") {
      const yes = await confirmDialog(
        "停止本轮并撤销挂单",
        "<p>停止后不再接受本轮 AI 操作，同时撤销本轮尚未成交的模拟挂单。已经模拟成交的订单保留。</p>",
        "停止并撤销",
        true,
      );
      if (yes) {
        await request(
          "/paper/ai/runs/" + encodeURIComponent(button.dataset.id) + "/stop",
          { method: "POST" },
        );
        notify("本轮已停止，未成交挂单已撤销");
        ui.renderRoute();
      }
    } else if (action === "paper-refresh-runs") {
      const runs = await request("/paper/ai/runs");
      document.querySelector("#paper-runs").innerHTML = runRows(runs);
      if (runs.some((r) => r.status === "running")) pollRuns(ui.signal());
    }
  } catch (e) {
    notify(e.message);
    const el = document.querySelector("#paper-contract-status");
    if (el && action === "paper-sync-hk") el.textContent = e.message;
  } finally {
    button.disabled = false;
  }
  return true;
}
