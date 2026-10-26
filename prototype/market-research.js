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
function updateIndexLive(data, selectedId, fallbackClose, fallbackDay) {
  const rows = new Map(data.indices.map((row) => [row.id, row]));
  for (const [id, row] of rows) {
    const card = [...document.querySelectorAll("[data-index-live]")].find((node) => node.dataset.indexLive === id);
    if (!card) continue;
    const price = card.querySelector("[data-index-price]");
    const change = card.querySelector("[data-index-change]");
    const status = card.querySelector("[data-index-status]");
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
  price.textContent = selected?.last == null ? number(fallbackClose) : number(selected.last);
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
  metrics.innerHTML = cells.map(([name, value]) =>
    '<div class="index-live-metric"><span>' + esc(name) + '</span><strong class="mono">' + esc(value) + '</strong></div>').join("");
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
        "资金与基金披露",
        "分别看来源估计资金、基金定期披露和数据覆盖。",
        `<button class="button" data-action="refresh-flow">${icon("refresh")}重新采集</button><button class="button primary" data-action="ask" data-question="分析沪深大盘近期资金历史，并明确北向资金、行业资金和基金披露的覆盖缺口。">${icon("spark")}询问 Agent</button>`,
      ) +
        panel(
          "资金数据覆盖",
          `<div class="metrics-list">${Object.entries(d.coverage || {})
            .map(
              ([key, value]) =>
                `<div class="metric-line"><span>${{ market: "大盘", stock: "个股", sector: "行业", fund: "公募基金", northbound: "北向资金" }[key]}</span><strong>${esc(value)}</strong></div>`,
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
        panel(
          "采集基金持仓披露",
          `<p class="field-help">每次1至5只中国公募基金，结果逐只缓存。基金公司定期披露存在时滞，不代表基金实时操作。</p><form id="fund-collect-form" class="section-gap"><div class="form-grid"><div class="form-row"><label class="field-label" for="fund-codes">基金代码</label><input id="fund-codes" class="field" name="codes" placeholder="例如 000001, 110022" required maxlength="80" aria-describedby="fund-collect-error"></div><div class="form-row"><label class="field-label" for="fund-year">披露年份</label><input id="fund-year" class="field" type="number" name="year" min="2000" max="${new Date().getFullYear()}" value="${new Date().getFullYear()}" required></div></div><p class="form-error" id="fund-collect-error" role="alert"></p><button type="submit" class="button primary">采集披露</button></form><div id="fund-collect-results" aria-live="polite"></div>`,
        ),
    ),
  );
}
export async function handleResearchSubmit(form, values, ui) {
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
  if (!["refresh-index", "refresh-flow", "collect-cycle"].includes(action))
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
