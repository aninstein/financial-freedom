import { request } from "./api.js";
import { stockOverview, mountStock, sectionMarkup } from "./stock.js";
import { esc, icon, number, percent, tone, time, stat, notify } from "./ui.js";
const indexHref = (id) => "#/indices/" + encodeURIComponent(id);
const scaled = (v) => (v == null ? "—" : percent(v * 100));
const panel = (title, body) =>
  `<section class="panel section-gap"><div class="panel-header"><h2>${title}</h2></div><div class="panel-body">${body}</div></section>`;
const states = {
  available: "已有数据",
  stale: "缓存已过期",
  error: "来源不可用",
  waiting: "等待采集",
  disabled: "采集已关闭",
  empty: "来源为空",
};
let indexTimer = null;
let indexRequest = null;
let indexVisibility = null;
export function cleanupIndices() {
  if (indexTimer) clearInterval(indexTimer);
  indexTimer = null;
  indexRequest?.abort();
  indexRequest = null;
  if (indexVisibility) document.removeEventListener("visibilitychange", indexVisibility);
  indexVisibility = null;
}
const liveTime = (value) => {
  if (!value) return "来源未提供行情时间";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) :
    date.toLocaleString("zh-CN", {timeZone: "Asia/Shanghai", hour12: false,
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"});
};
const liveState = (row) =>
  row.last == null ? "暂无盘中快照" :
  row.market_session === "preopen" || row.market_session === "pre_market" ? "盘前 · 最近记录" :
  row.market_session === "break" ? "午间休市 · 最近记录" :
  row.market_session !== "open" ? "休市 · 最近记录" :
  row.source_time && row.source_age_seconds > 45 ? "行情时间已过期" :
  row.state === "stale" ? "采集已中断" :
  row.source_time ? row.feed === "push" ? "订阅更新" : "批量快照" :
  "行情时间待核实";
function flashIndexBlock(node, changePercent) {
  if (!node || changePercent == null || Number(changePercent) === 0 ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const className = Number(changePercent) > 0 ? "index-flash-up" : "index-flash-down";
  node.classList.remove("index-flash-up", "index-flash-down");
  void node.offsetWidth;
  node.classList.add(className);
  node.addEventListener("animationend", () => node.classList.remove(className), { once: true });
}
function updateIndexLive(data, selectedId, fallbackClose, fallbackDay) {
  const rows = new Map(data.indices.map((row) => [row.id, row]));
  for (const [id, row] of rows) {
    const card = [...document.querySelectorAll("[data-index-live]")].find((node) => node.dataset.indexLive === id);
    if (!card) continue;
    const price = card.querySelector("[data-index-price]");
    const change = card.querySelector("[data-index-change]");
    const status = card.querySelector("[data-index-status]");
    const previousPrice = card.dataset.lastPrice;
    const nextPrice = row.last == null ? "" : String(row.last);
    if (previousPrice && nextPrice && previousPrice !== nextPrice) flashIndexBlock(card, row.change_percent);
    card.dataset.lastPrice = nextPrice;
    price.textContent = row.last == null ? "—" : number(row.last);
    change.textContent = row.change_percent == null ? "—" : percent(row.change_percent);
    change.className = "mono " + (row.change_percent == null ? "" : tone(row.change_percent));
    status.textContent = liveState(row);
  }
  const selected = rows.get(selectedId);
  const price = document.querySelector("#index-current-price");
  const label = document.querySelector("#index-current-label");
  const status = document.querySelector("#index-live-status");
  const source = document.querySelector("#index-live-source");
  const metrics = document.querySelector("#index-live-metrics");
  const cadence = document.querySelector("#index-live-cadence");
  if (cadence) cadence.textContent = data.provider === "futu"
    ? "每秒同步本机 · " + liveTime(data.served_at) + " · 富途 OpenD 行情源；采样间隔见数据与模型"
    : data.provider === "longbridge"
    ? "每秒同步本机 · " + liveTime(data.served_at) +
      (data.longbridge_connected ? " · 订阅源已连接" : " · 订阅源尚未连接，保留公共快照")
    : data.provider === "akshare"
      ? "每秒同步本机 · " + liveTime(data.served_at) + " · AKShare 当前采集间隔至少 " + data.current_poll_seconds + " 秒"
      : "每秒同步本机 · " + liveTime(data.served_at) + " · 指数采集未启用";
  if (!price || !label || !status || !source || !metrics) return;
  const nextSelectedPrice = selected?.last == null ? number(fallbackClose) : number(selected.last);
  if (price.dataset.liveValue && price.dataset.liveValue !== nextSelectedPrice)
    flashIndexBlock(price.parentElement, selected?.change_percent);
  price.dataset.liveValue = nextSelectedPrice;
  price.textContent = nextSelectedPrice;
  label.textContent = selected?.last == null ? "最近完整日线收盘 · " + (fallbackDay || "暂无") : "盘中指数点位";
  const currentStatus = selected ? liveState(selected) : "暂无盘中快照";
  if (status.textContent !== currentStatus) status.textContent = currentStatus;
  source.textContent = selected?.last == null
    ? "尚无可用盘中报价。日K与历史统计独立更新。" +
      (Object.values(data.source_errors || {}).length ? " 数据源：" + Object.values(data.source_errors).slice(0, 2).join("；") : "")
    : selected.source + " · 行情 " + liveTime(selected.source_time) + " · 接收 " + liveTime(selected.received_at) +
      " · " + (selected.feed === "push" ? "上游订阅推送" : "上游批量采样") +
      " · " + (selected.source_time ? "来源时间可核实" : "来源未返回行情时间，延迟未知");
  const cells = [
    ["涨跌幅", selected?.change_percent == null ? "—" : percent(selected.change_percent)],
    ["昨收", number(selected?.previous_close)],
    ["今开", number(selected?.open)],
    ["最高", number(selected?.high)],
    ["最低", number(selected?.low)],
    ["成交量 · 源单位", number(selected?.volume, 0)],
    ["成交额 · 源单位", number(selected?.turnover, 0)],
  ];
  if (metrics.children.length !== cells.length)
    metrics.innerHTML = cells.map(([name]) =>
      '<div class="index-live-metric"><span>' + esc(name) + '</span><strong class="mono">—</strong></div>').join("");
  cells.forEach(([, value], index) => {
    const cell = metrics.children[index];
    const strong = cell.querySelector("strong");
    if (strong.textContent !== "—" && strong.textContent !== value)
      flashIndexBlock(cell, selected?.change_percent);
    strong.textContent = value;
    if (index === 0) strong.className = "mono " + tone(selected?.change_percent);
  });
}
export function mountIndexLive(selectedId, fallbackClose, fallbackDay, routeSignal) {
  cleanupIndices();
  const pull = async () => {
    if (document.hidden || routeSignal.aborted || indexRequest) return;
    const controller = new AbortController();
    indexRequest = controller;
    try {
      const data = await request("/workspace/indices/live", {signal: controller.signal, timeout: 3000});
      if (!controller.signal.aborted && !routeSignal.aborted)
        updateIndexLive(data, selectedId, fallbackClose, fallbackDay);
    } catch (error) {
      if (!controller.signal.aborted && !routeSignal.aborted) {
        const status = document.querySelector("#index-live-status");
        if (status) status.textContent = "本机行情连接中断，保留上次数据";
      }
    } finally {
      if (indexRequest === controller) indexRequest = null;
    }
  };
  indexVisibility = () => { if (!document.hidden) pull(); };
  document.addEventListener("visibilitychange", indexVisibility);
  indexTimer = setInterval(pull, 1000);
  pull();
}
function indexCardsMarkup(catalog, selectedId) {
  return catalog.map((item) =>
    '<a class="index-live-card ' + (item.id === selectedId ? 'active' : '') +
    '" href="' + indexHref(item.id) + '" data-index-live="' + esc(item.id) + '"' +
    (item.id === selectedId ? ' aria-current="page"' : '') + '>' +
    '<span>' + esc(item.name) + '</span><strong class="mono" data-index-price>—</strong>' +
    '<small class="mono" data-index-change>—</small><small data-index-status>等待快照</small></a>'
  ).join('');
}
function indexLiveMarkup(catalog, selected, lastBar) {
  return '<section class="panel index-live-panel section-gap" aria-label="大盘指数快照">' +
    '<div class="panel-header"><div><h2>大盘快照</h2><p id="index-live-cadence">正在读取本机行情快照…</p></div>' +
    '<span class="tag" id="index-live-status" role="status">正在连接</span></div>' +
    '<div class="index-live-feature"><div><span class="eyebrow">' + esc(selected.name) + '</span>' +
    '<strong class="mono" id="index-current-price">' + number(lastBar?.close) + '</strong>' +
    '<small id="index-current-label">最近完整日线收盘 · ' + esc(lastBar?.bar_time || '暂无') + '</small></div>' +
    '<div class="index-live-metrics" id="index-live-metrics"></div></div>' +
    '<p class="field-help index-live-source" id="index-live-source">正在读取快照来源与时间…</p>' +
    '<div class="index-live-grid">' + indexCardsMarkup(catalog, selected.id) + '</div></section>';
}
export async function mountMarketIndices(signal) {
  const holder = document.querySelector("#market-index-strip");
  if (!holder) return;
  try {
    const catalog = await request("/workspace/indices", {signal, timeout: 4000});
    if (signal.aborted || !document.contains(holder)) return;
    holder.innerHTML = '<section class="panel index-live-panel section-gap" aria-label="大盘指数快照">' +
      '<div class="panel-header"><div><h2>主要指数</h2><p id="index-live-cadence">正在读取本机行情快照…</p></div>' +
      '<a class="text-link" href="#/indices">完整指数分析 →</a></div>' +
      '<div class="index-live-grid">' + indexCardsMarkup(catalog, null) + '</div></section>';
    mountIndexLive(null, null, null, signal);
  } catch {
    if (!signal.aborted && document.contains(holder))
      holder.textContent = "指数目录暂不可用，市场行情表可继续查看。";
  }
}
export function cycleMarkup(data) {
  const season = data.seasonality || [];
  return `${data.observations < 20 ? `<div class="alert">完整日线不足，当前 ${data.observations} 条。请先拉取历史数据。</div>` : ""}<div class="stat-grid">${stat("趋势结构 · MA20/60", { upward: "向上排列", downward: "向下排列", mixed: "交错 / 震荡", insufficient: "样本不足" }[data.trend])}${stat("20日年化波动", scaled(data.annualized_volatility_20d))}${stat("样本最大回撤", scaled(data.max_drawdown))}${stat("完整日线", number(data.observations, 0) + " 根")}</div><p class="field-help section-gap">${esc(data.first_bar || "暂无")} — ${esc(data.last_bar || "暂无")} · 接收 ${time(data.received_at)} · 非复权收盘价 · ${esc(data.source?.join(" / ") || "尚无来源")}</p>${data.data_gaps?.map((x) => `<p class="field-help">${esc(x)}</p>`).join("") || ""}${panel("阶段收益", `<div class="table-scroll"><table class="data-table"><thead><tr><th>交易观测周期</th><th>涨跌幅</th></tr></thead><tbody>${data.horizons.map((x) => `<tr><td>${x.sessions} 根日线</td><td class="mono ${tone(x.return)}">${scaled(x.return)}</td></tr>`).join("")}</tbody></table></div>`)}${panel("月度季节性", `<p class="field-help">同一自然月的历史月收益分布；本月不计入。每月少于3次标为样本不足，正收益比例不是未来上涨概率。</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>月份</th><th>样本数</th><th>平均收益</th><th>中位收益</th><th>历史正收益比例</th></tr></thead><tbody>${season.map((x) => `<tr><td>${x.month} 月${x.sample_sufficient ? "" : " · 样本不足"}</td><td>${x.observations}</td><td class="mono ${tone(x.mean_return)}">${scaled(x.mean_return)}</td><td class="mono">${scaled(x.median_return)}</td><td>${x.positive_fraction == null ? "—" : number(x.positive_fraction * 100) + "%"}</td></tr>`).join("")}</tbody></table></div>`)}${panel("收益自相关", `<p class="field-help">衡量日收益与滞后日收益的相关性，不能解释为未来价格周期；至少需要60对且不少于3倍滞后周期的样本对。</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>滞后交易观测</th><th>有效样本对</th><th>相关系数</th></tr></thead><tbody>${data.return_autocorrelation.map((x) => `<tr><td>${x.lag_sessions}</td><td>${x.pairs}</td><td>${number(x.return_autocorrelation, 4)}</td></tr>`).join("")}</tbody></table></div>`)}<details class="section-gap"><summary>统计方法与可复现信息</summary><p class="field-help">${esc(data.method_note)}</p><p class="field-help">${esc(data.interpretation_note)}</p><p class="field-help">${esc(data.method_version)} · 样本 SHA-256 ${esc(data.sample_hash)}</p></details>`;
}
export async function renderIndices(r, signal, ui) {
  const catalog = await request("/workspace/indices", { signal });
  const selected =
    catalog.find((x) => x.id === r.id) || (!r.id ? catalog[0] : null);
  if (!selected) throw new Error("没有这个指数，请从指数目录进入。");
  const d = await request(
    "/workspace/indices/" + encodeURIComponent(selected.id),
    { signal, timeout: 24000 },
  );
  if (signal.aborted) return;
  ui.setPage(
    ui.page(
      ui.heading(
        "大盘与指数",
        "大盘快照每秒在页面同步；日K与历史周期独立计算。",
        `<button class="button" data-action="refresh-index" data-id="${esc(selected.id)}">${icon("refresh")}重新采集</button><button class="button primary" data-action="ask" data-question="请分析 ${esc(selected.name)}（${esc(selected.id)}）的阶段趋势、历史周期统计和数据缺口，使用指数工具并引用证据。">${icon("spark")}询问 Agent</button>`,
      ) +
        `<nav class="route-tabs section-gap" aria-label="指数目录">${catalog.map((x) => `<a class="route-tab ${x.id === selected.id ? "active" : ""}" href="${indexHref(x.id)}" ${x.id === selected.id ? 'aria-current="page"' : ""}>${esc(x.name)}</a>`).join("")}</nav><div class="page-heading section-gap"><div><h2>${esc(selected.name)}</h2><p>${esc(selected.id)} · ${states[d.state] || esc(d.state)} · 历史日线收盘</p></div><div class="detail-price mono">${number(d.bars.at(-1)?.close)}</div></div>${d.error ? `<div class="alert">${esc(d.error)}${d.bars.length ? "，以下保留上次成功数据。" : ""}</div>` : ""}${stockOverview(d, r)}<div class="section-gap">${cycleMarkup(d.analysis)}</div>`,
    ),
  );
  document.querySelector('nav[aria-label="指数目录"]')?.insertAdjacentHTML(
    "afterend", indexLiveMarkup(catalog, selected, d.bars.at(-1))
  );
  mountStock(d, r, signal);
  mountIndexLive(selected.id, d.bars.at(-1)?.close, d.bars.at(-1)?.bar_time, signal);
}
export async function renderFlows(r, signal, ui) {
  const d = await request("/research/flows", { signal, timeout: 24000 });
  if (signal.aborted) return;
  const rows = d.rows || [],
    page = Math.max(
      1,
      Math.min(
        Math.ceil(rows.length / 20) || 1,
        Number(r.params.get("page")) || 1,
      ),
    );
  const start = (page - 1) * 20;
  ui.setPage(
    ui.page(
      ui.heading(
        "资金流向",
        "查看大盘成交分类、行业主力资金和北向收盘后数据。",
        `<button class="button" data-action="refresh-flow">${icon("refresh")}重新采集</button><button class="button primary" data-action="ask" data-question="分析沪深大盘近期资金历史，并明确北向资金、行业资金和基金披露的覆盖缺口。">${icon("spark")}询问 Agent</button>`,
      ) +
        panel(
          "资金数据覆盖",
          `<div class="metrics-list">${Object.entries(d.coverage || {})
            .map(
              ([key, value]) =>
                `<div class="metric-line"><span>${{ market: "大盘", stock: "个股", sector: "行业", northbound: "北向资金" }[key]}</span><strong>${esc(value)}</strong></div>`,
            )
            .join(
              "",
            )}</div><a class="text-link section-gap" href="#/sectors">打开行业板块 →</a>`,
        ) +
        panel(
          "沪深大盘资金历史",
          sectionMarkup({
            ...d,
            label: "大盘资金",
            rows: rows.slice(start, start + 20),
            unit_note: d.note,
          }) +
            `<div class="table-footer"><span>${rows.length} 条缓存 · 第 ${page} 页</span>${page > 1 ? `<a class="button small" href="#/flows?page=${page - 1}">上一页</a>` : ""}${start + 20 < rows.length ? `<a class="button small" href="#/flows?page=${page + 1}">下一页</a>` : ""}</div>`,
        ) +
        panel("行业资金流入排行", `<p class="field-help">${esc(d.sectors?.note || d.sectors?.error || "暂无来源说明")}</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>行业</th><th>涨跌幅</th><th>${esc(d.sectors?.flow_metric || "资金净额")} · 元</th><th>净占比</th></tr></thead><tbody>${(d.sectors?.rows || []).map((x) => `<tr><td>${esc(x.name)}</td><td class="mono ${tone(x.change_percent)}">${percent(x.change_percent)}</td><td class="mono ${tone(x.net_flow_yuan)}">${number(x.net_flow_yuan, 0)}</td><td class="mono">${percent(x.main_net_ratio_percent)}</td></tr>`).join("") || '<tr><td colspan="4">行业资金暂不可用</td></tr>'}</tbody></table></div><p class="field-help">${esc(d.sectors?.source || "来源未取得")} · ${esc(d.sectors?.state || "等待")} · 接收 ${time(d.sectors?.received_at)}</p>`)+
        panel("北向资金 · 收盘后披露", `<p class="field-help">${esc(d.northbound?.note || d.northbound?.error || "暂无来源说明")}</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>日期</th><th>成交净买额 · 来源原值</th><th>买入 / 卖出 · 来源原值</th><th>成交额 · 来源原值</th><th>成交笔数</th></tr></thead><tbody>${(d.northbound?.rows || []).map((x) => `<tr><td>${esc(x.date)}</td><td class="mono ${tone(x.net_buy)}">${number(x.net_buy)}</td><td class="mono">${number(x.buy)} / ${number(x.sell)}</td><td class="mono">${number(x.turnover)}</td><td class="mono">${number(x.deal_count,0)}</td></tr>`).join("") || '<tr><td colspan="5">北向历史暂不可用</td></tr>'}</tbody></table></div><p class="field-help">${esc(d.northbound?.state || "等待")} · 接收 ${time(d.northbound?.received_at)}</p>`),
    ),
  );
}

const fundHref = (code) => "#/funds/" + encodeURIComponent(code);
const fundMetric = (label, value) => `<div class="metric-line"><span>${esc(label)}</span><strong>${esc(value || "—")}</strong></div>`;
export async function renderFunds(r, signal, ui) {
  if (r.id) {
    const d = await request("/research/funds/" + encodeURIComponent(r.id), {signal, timeout: 35000});
    if (signal.aborted) return;
    const basic = d.basic || {}, nav = d.latest_nav || {}, history = d.nav_history || [];
    const weights = (d.holdings || []).filter((x) => x.weight_percent != null).map((x) => Number(x.weight_percent)).filter(Number.isFinite);
    const topWeight = weights.reduce((sum, x) => sum + x, 0);
    const allocation = d.asset_allocation || {};
    ui.setPage(ui.page(ui.heading(esc(d.name || r.id), `${esc(d.code)} · ${esc(d.fund_type || "类型待核实")} · ${esc(d.venue || "交易场所待核实")}`,
      `<button class="button" data-action="refresh-fund" data-code="${esc(d.code)}">${icon("refresh")}同步详情</button><button class="button primary" data-action="ask" data-question="分析基金 ${esc(d.code)} 的历史收益、经理、费用、最新披露持仓集中度与风险；逐项引用数据日期，并说明净值估算和申购状态的缺口。">${icon("spark")}询问 Agent</button>`) +
      `<a class="text-link" href="#/funds">← 返回基金目录</a>${d.error ? `<div class="alert section-gap">${esc(d.error)}</div>` : ""}` +
      `<div class="stat-grid section-gap">${stat("最近公布单位净值", number(nav.nav, 4), nav.date || "暂无")}${stat("净值日涨跌", `<span class="${tone(nav.daily_change_percent)}">${percent(nav.daily_change_percent)}</span>`, "按最近公布净值")}${stat("近一年收益", `<span class="${tone(d.returns_percent?.["1y"])}">${percent(d.returns_percent?.["1y"])}</span>`, "来源阶段收益")}${stat("前十大披露持仓占比", weights.length ? percent(topWeight) : "—", d.holdings_report || "暂无披露")}${d.venue === "场内" ? stat("场内行情快照", number(d.exchange_quote?.last, 4), d.exchange_quote?.source_time ? `行情 ${time(d.exchange_quote.source_time)}` : "行情时点未核实") + stat("场内涨跌幅", `<span class="${tone(d.exchange_quote?.change_percent)}">${percent(d.exchange_quote?.change_percent)}</span>`, "与基金净值分开") : ""}</div>`+
      panel("收益与净值", `<div class="metrics-list">${[["近1月", "1m"],["近3月", "3m"],["近6月", "6m"],["近1年", "1y"]].map(([label, key]) => fundMetric(label, percent(d.returns_percent?.[key]))).join("")}</div><p class="field-help section-gap">${esc(d.estimate_note || "当日估算来源未提供")}</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>净值日期</th><th>单位净值</th><th>当日涨跌</th></tr></thead><tbody>${history.slice(-30).reverse().map((x) => `<tr><td>${esc(x.date)}</td><td class="mono">${number(x.nav,4)}</td><td class="mono ${tone(x.daily_change_percent)}">${percent(x.daily_change_percent)}</td></tr>`).join("") || '<tr><td colspan="3">暂无历史净值</td></tr>'}</tbody></table></div><p class="field-help">展示最近30条 / 已同步${history.length}条历史净值；单位净值不是ETF盘中成交价。</p>`)+
      panel("净值风险统计", `<div class="metrics-list">${fundMetric("净值观测数",number(d.analysis?.observations,0))}${fundMetric("年化净值波动",percent(d.analysis?.volatility_percent))}${fundMetric("样本最大回撤",percent(d.analysis?.max_drawdown_percent))}${fundMetric("统计区间",d.analysis?.first_date && d.analysis?.last_date ? `${d.analysis.first_date} — ${d.analysis.last_date}` : null)}</div><p class="field-help section-gap">${esc(d.analysis?.note)}</p>`)+
      panel("基金经理与基金公司", `<div class="metrics-list">${fundMetric("管理人",basic.company)}${fundMetric("托管人",basic.custodian)}${fundMetric("成立日期 / 规模",basic.founded)}${fundMetric("资产规模",basic.asset_size)}${fundMetric("现任基金经理",(d.managers || []).map((x) => x.name).filter(Boolean).join("、"))}${fundMetric("申购状态",d.purchase_status)}${fundMetric("赎回状态",d.redemption_status)}${fundMetric("业绩比较基准",basic.benchmark)}${fundMetric("跟踪标的",basic.tracking_target)}</div>${basic.company_url ? `<a class="text-link section-gap" href="${esc(basic.company_url)}" target="_blank" rel="noopener noreferrer">查看基金公司档案 ↗</a>` : ""}`)+
      panel("费用", `<div class="metrics-list">${fundMetric("管理费率",basic.management_fee)}${fundMetric("托管费率",basic.custody_fee)}${fundMetric("销售服务费率",basic.sales_service_fee)}${fundMetric("最高申购费率",basic.purchase_fee)}${fundMetric("最高赎回费率",basic.redemption_fee)}</div><p class="field-help section-gap">管理费与托管费通常计入基金净值；实际交易费用以基金公告和交易平台为准。</p>`)+
      panel("定期披露持仓", `<p class="field-help">${esc(d.holdings_report || "暂无可用持仓披露")} · 定期披露有时滞，不代表今日持仓。</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>证券</th><th>占净值比例</th><th>持仓市值 · 万元</th></tr></thead><tbody>${(d.holdings || []).map((x) => `<tr><td>${esc(x.name)} ${esc(x.code)}</td><td class="mono">${percent(x.weight_percent)}</td><td class="mono">${number(x.market_value_10k)}</td></tr>`).join("") || '<tr><td colspan="3">当前类型或来源未返回持仓明细</td></tr>'}</tbody></table></div><p class="field-help">前十大合计 ${weights.length ? percent(topWeight) : "—"}；仅反映已披露${d.holdings_kind === "bond" ? "债券" : "股票"}仓位。</p>`)+
      panel("近期披露变化", `<p class="field-help">${esc(d.previous_holdings_report || "上一期持仓未取得")} → ${esc(d.holdings_report || "本期持仓未取得")}。以下只比较两期均进入前十大证券的权重变化，单位为百分点；不代表期间真实买卖。</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>证券</th><th>上期占比</th><th>本期占比</th><th>变化</th></tr></thead><tbody>${(d.holding_weight_changes || []).map((x) => `<tr><td>${esc(x.name)} ${esc(x.code)}</td><td>${percent(x.previous_weight_percent)}</td><td>${percent(x.weight_percent)}</td><td class="mono ${tone(x.change_pp)}">${percent(x.change_pp)}</td></tr>`).join("") || '<tr><td colspan="4">缺少可比较的两期持仓</td></tr>'}</tbody></table></div>`)+
      panel("资产配置与研究口径", `<p class="field-help">${esc((allocation.categories || []).join("、") || "资产配置暂无可用报告期")}</p><div class="metrics-list section-gap">${(allocation.series || []).map((x) => fundMetric(x.name, (x.data || []).map((v) => v == null ? "—" : number(v) + "%").join(" / "))).join("") || fundMetric("资产配置", "暂无")}</div><p class="field-help section-gap">持仓与资产配置来自定期披露，不推断日内调仓。申购、赎回状态以当前来源返回值展示，交易前仍需向交易平台核对。</p><a class="text-link" href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">查看天天基金原始页面 ↗</a><p class="field-help">${esc(d.source)} · 来源 ${time(d.source_time)} · 同步 ${time(d.received_at)} · ${esc(d.state)}</p>`)
    ));
    return;
  }
  const q = r.params.get("q") || "", category = r.params.get("category") || "all";
  const page = Math.max(1, Number(r.params.get("page")) || 1);
  const params = new URLSearchParams({q,category,page:String(page)});
  const d = await request("/research/funds?" + params, {signal, timeout: 35000});
  if (signal.aborted) return;
  const href = (p) => `#/funds?q=${encodeURIComponent(q)}&category=${encodeURIComponent(category)}&page=${p}`;
  ui.setPage(ui.page(ui.heading("公募基金", "搜索东方财富基金目录，查看净值、收益、经理、费用和定期披露。",
    `<button class="button" data-action="refresh-funds">${icon("refresh")}同步目录</button>`) +
    `${d.error ? `<div class="alert">${esc(d.error)}</div>` : ""}<form id="fund-search-form" class="fund-search-form section-gap" novalidate role="search"><div class="form-row"><label class="field-label" for="fund-query">基金名称或代码</label><input class="field" id="fund-query" name="query" value="${esc(q)}" maxlength="80" placeholder="例如 债券、ETF、QDII、110022"></div><div class="form-row"><label class="field-label" for="fund-category">类型</label><select class="field" id="fund-category" name="category"><option value="all">全部类型</option>${Object.entries(d.categories || {}).map(([name,count]) => `<option value="${esc(name)}" ${name === category ? "selected" : ""}>${esc(name)} · ${number(count,0)}</option>`).join("")}</select></div><button class="button primary" type="submit">搜索基金</button>${q ? '<a class="button small" href="#/funds">清空搜索</a>' : ""}</form>`+
    panel("基金目录", `<p class="field-help">${number(d.total,0)} 只结果 · ${esc(d.source)} · 同步 ${time(d.updated_at)} · ${esc(d.state)}。${esc(d.coverage_note)}</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>基金</th><th>类型</th><th>交易场所</th><th>查看</th></tr></thead><tbody>${(d.rows || []).map((x) => `<tr><td><a class="text-link" href="${fundHref(x.code)}">${esc(x.name)}</a><small class="fund-code">${esc(x.code)}</small></td><td>${esc(x.fund_type || "待核实")}</td><td>${esc(x.venue)}</td><td><a class="text-link" href="${fundHref(x.code)}">分析 →</a></td></tr>`).join("") || '<tr><td colspan="4">没有符合条件的基金，请调整关键词或类型。</td></tr>'}</tbody></table></div><div class="table-footer"><span>第 ${d.page} 页 · 每页 ${d.page_size} 只</span>${d.page > 1 ? `<a class="button small" href="${href(d.page - 1)}">上一页</a>` : ""}${d.page * d.page_size < d.total ? `<a class="button small" href="${href(d.page + 1)}">下一页</a>` : ""}</div>`)
  ));
}
export async function handleResearchSubmit(form, values, ui) {
  if (form.id === "fund-search-form") {
    location.hash = `/funds?q=${encodeURIComponent((values.query || "").trim())}&category=${encodeURIComponent(values.category || "all")}&page=1`;
    return true;
  }
  if (form.id !== "fund-collect-form") return false;
  const codes = [...new Set(values.codes.trim().split(/[,，\s]+/))];
  const error = document.querySelector("#fund-collect-error");
  error.textContent = "";
  if (codes.length > 5 || codes.some((x) => !/^\d{6}$/.test(x))) {
    error.textContent = "请填写1至5个六位基金代码，用逗号分隔。";
    return true;
  }
  await ui.busy(form.querySelector("button[type=submit]"), async () => {
    try {
      const d = await request("/research/funds/collect", {
        method: "POST",
        body: { codes, year: Number(values.year) },
        timeout: 65000,
        signal: ui.signal(),
      });
      const holder = document.querySelector("#fund-collect-results");
      if (holder)
        holder.innerHTML = d.funds
          .map((x) =>
            panel(
              `基金 ${esc(x.fund_code)} · ${esc(x.year)}年`,
              sectionMarkup({
                ...x,
                unit_note: x.note,
                rows: x.rows?.slice(0, 30),
              }) +
                `<p class="field-help">展示前30条 / 缓存 ${x.rows?.length || 0} 条</p><button class="button small" data-action="ask" data-question="请分析基金 ${esc(x.fund_code)} 在 ${x.year} 年披露的持仓集中度、行业分布与主要风险，引用报告期，说明是否覆盖全年。">让 Agent 分析</button>`,
            ),
          )
          .join("");
    } catch (e) {
      if (document.contains(error)) error.textContent = e.message;
    }
  });
  return true;
}
export async function handleResearchAction(button, ui) {
  const action = button.dataset.action;
  if (!["refresh-index", "refresh-flow", "refresh-funds", "refresh-fund", "collect-cycle"].includes(action))
    return false;
  await ui.busy(button, async () => {
    try {
      if (action === "refresh-index")
        await request(
          "/workspace/indices/" +
            encodeURIComponent(button.dataset.id) +
            "?refresh=true",
          { signal: ui.signal(), timeout: 24000 },
        );
      if (action === "refresh-flow")
        await request("/research/flows?refresh=true", {
          signal: ui.signal(),
          timeout: 24000,
        });
      if (action === "refresh-funds")
        await request("/research/funds?refresh=true", {signal: ui.signal(), timeout: 35000});
      if (action === "refresh-fund")
        await request("/research/funds/" + encodeURIComponent(button.dataset.code) + "?refresh=true", {signal: ui.signal(), timeout: 35000});
      if (action === "collect-cycle") {
        const end = new Date(),
          start = new Date(end);
        start.setFullYear(start.getFullYear() - 5);
        await request(
          "/bars/pull?instrument_id=" +
            encodeURIComponent(button.dataset.id) +
            "&start=" +
            start.toISOString().slice(0, 10) +
            "&end=" +
            end.toISOString().slice(0, 10),
          { method: "POST", signal: ui.signal(), timeout: 40000 },
        );
      }
      notify("数据请求已完成，来源状态以页面结果为准");
      await ui.renderRoute();
    } catch (e) {
      notify(e.message, "error");
    }
  });
  return true;
}
