import { request } from "./api.js";
import {
  esc,
  icon,
  number,
  percent,
  time,
  empty,
  loading,
  stockHref,
} from "./ui.js";
const $ = (s) => document.querySelector(s);
const labels = {
  profile: "公司概况",
  snapshot: "盘口与估值",
  financials: "财务摘要",
  ownership: "股东户数",
  dividends: "分红记录",
  flow: "资金流向",
  news: "相关新闻",
  announcements: "公司公告",
  income: "利润表",
  balance: "资产负债表",
  cashflow: "现金流量表",
  holders: "十大股东",
  business: "主营构成",
  reports: "机构研报目录",
};
const stateNames = {
  available: "已取得",
  empty: "来源暂无记录",
  partial: "部分可用",
  stale: "过期缓存",
  unsupported: "未接入",
  error: "连接异常",
};
const num = (v) => (v != null && Number.isFinite(Number(v)) ? Number(v) : null);
function validBars(bars) {
  return bars.filter(
    (b) =>
      [b.open, b.high, b.low, b.close].every((x) => num(x) != null) &&
      b.high >= Math.max(b.open, b.close) &&
      b.low <= Math.min(b.open, b.close) &&
      b.high >= b.low,
  );
}
export function aggregateBars(bars, period) {
  if (period === "day") return validBars(bars);
  const groups = new Map();
  for (const b of validBars(bars)) {
    const date = new Date(b.bar_time + "T00:00:00Z");
    let key = b.bar_time.slice(0, 7);
    if (period === "week") {
      const day = (date.getUTCDay() + 6) % 7;
      date.setUTCDate(date.getUTCDate() - day);
      key = date.toISOString().slice(0, 10);
    }
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(b);
  }
  return [...groups.values()].map((rows) => ({
    bar_time: rows[0].bar_time,
    end_time: rows.at(-1).bar_time,
    open: rows[0].open,
    close: rows.at(-1).close,
    high: Math.max(...rows.map((x) => x.high)),
    low: Math.min(...rows.map((x) => x.low)),
    volume: rows.every((x) => num(x.volume) != null)
      ? rows.reduce((sum, x) => sum + Number(x.volume), 0)
      : null,
    volume_unit: rows.every((x) => x.volume_unit === rows[0].volume_unit)
      ? rows[0].volume_unit
      : "unknown",
    amount: rows.every((x) => num(x.amount) != null)
      ? rows.reduce((sum, x) => sum + Number(x.amount), 0)
      : null,
  }));
}
function series(bars, window) {
  return bars.map((b, i) =>
    i + 1 < window
      ? null
      : bars
          .slice(i - window + 1, i + 1)
          .reduce((s, v) => s + Number(v.close), 0) / window,
  );
}
const maColors = { 5: "#f4ce7b", 10: "#b69af4", 20: "#76baf5", 60: "#e896aa" };
export function chartSVG(all, start, end) {
  const bars = all.slice(start, end),
    width = 1040,
    left = 66,
    right = 986,
    top = 26,
    bottom = 330,
    vTop = 376,
    vBottom = 458;
  const highs = bars.map((b) => Number(b.high)),
    lows = bars.map((b) => Number(b.low));
  let min = Math.min(...lows),
    max = Math.max(...highs);
  let margin = Math.max((max - min) * 0.08, max * 0.005, 0.01);
  min -= margin;
  max += margin;
  const y = (v) => bottom - ((v - min) / (max - min)) * (bottom - top);
  const step = (right - left) / bars.length,
    body = Math.max(0.8, Math.min(12, step * 0.65));
  const x = (i) => left + step * (i + 0.5);
  const volMax = Math.max(1, ...bars.map((b) => num(b.volume) || 0));
  let paths = "";
  for (const window of [5, 10, 20, 60]) {
    const values = series(all, window).slice(start, end);
    const path = values
      .map((v, i) =>
        v == null
          ? ""
          : `${i === 0 || values[i - 1] == null ? "M" : "L"}${x(i).toFixed(2)},${y(v).toFixed(2)}`,
      )
      .join(" ");
    paths += `<path d="${path}" stroke="${maColors[window]}" stroke-width="1.2" fill="none" vector-effect="non-scaling-stroke"/>`;
  }
  const grid = [0, 0.25, 0.5, 0.75, 1]
    .map(
      (t) =>
        `<line x1="${left}" x2="${right}" y1="${top + t * (bottom - top)}" y2="${top + t * (bottom - top)}" class="chart-grid"/><text x="8" y="${top + t * (bottom - top) + 4}" class="chart-label">${number(max - t * (max - min))}</text>`,
    )
    .join("");
  return `<svg class="candlestick-chart" viewBox="0 0 ${width} 500" tabindex="0" role="img" aria-label="${esc(bars[0].bar_time)} 至 ${esc(bars.at(-1).end_time || bars.at(-1).bar_time)} 的真实 OHLC 蜡烛图和成交量。使用左右方向键检查单根K线。" data-chart-start="${start}" data-chart-count="${bars.length}">${grid}<text x="${left}" y="363" class="chart-label">成交量 · ${volumeUnit(bars)}</text><line x1="${left}" x2="${right}" y1="${vBottom}" y2="${vBottom}" class="chart-grid"/>${bars
    .map((b, i) => {
      const up = Number(b.close) >= Number(b.open),
        color = up ? "var(--market-up)" : "var(--market-down)";
      return `<g data-candle="${i}" tabindex="-1"><line x1="${x(i)}" x2="${x(i)}" y1="${y(b.high)}" y2="${y(b.low)}" stroke="${color}" stroke-width="1"/><rect x="${x(i) - body / 2}" y="${Math.min(y(b.open), y(b.close))}" width="${body}" height="${Math.max(1, Math.abs(y(b.open) - y(b.close)))}" fill="${up ? "var(--surface)" : color}" stroke="${color}" stroke-width="1"/>${num(b.volume) != null ? `<rect x="${x(i) - body / 2}" y="${vBottom - (Number(b.volume) / volMax) * (vBottom - vTop)}" width="${body}" height="${(Number(b.volume) / volMax) * (vBottom - vTop)}" fill="${color}" opacity=".7"/>` : ""}<rect x="${left + i * step}" y="${top}" width="${step}" height="${vBottom - top}" fill="transparent" data-hit="${i}"/></g>`;
    })
    .join(
      "",
    )}${paths}${[0, Math.floor(bars.length / 2), bars.length - 1].map((i) => `<text x="${x(i)}" y="487" class="chart-label" text-anchor="middle">${esc(bars[i].bar_time)}</text>`).join("")}<g id="chart-crosshair" visibility="hidden"><line id="chart-crosshair-x" y1="${top}" y2="${vBottom}" class="crosshair"/></g></svg>`;
}
function volumeUnit(bars) {
  const units = new Set(bars.map((b) => b.volume_unit || "unknown"));
  return units.size === 1
    ? { shares: "股", lots: "手", grams: "克", unknown: "来源原始单位" }[
        [...units][0]
      ] || "来源原始单位"
    : "来源单位不统一";
}
function sampleInfo(bar, all, index) {
  const previous = all[index - 1]?.close,
    change = previous ? Number(bar.close) / Number(previous) - 1 : null;
  return `<strong>${esc(bar.bar_time)}${bar.end_time && bar.end_time !== bar.bar_time ? " — " + esc(bar.end_time) : ""}</strong><span>开 <b>${number(bar.open)}</b></span><span>高 <b>${number(bar.high)}</b></span><span>低 <b>${number(bar.low)}</b></span><span>收 <b>${number(bar.close)}</b></span><span>涨跌 <b class="${change != null && change >= 0 ? "candle-up" : "candle-down"}">${change == null ? "—" : percent(change * 100)}</b></span><span>量 <b>${number(bar.volume, 0)}</b></span>`;
}
const chartHref = (d, r) =>
  d.index
    ? r?.id ? "#/indices/" + encodeURIComponent(d.instrument_id) : "#/indices"
    : stockHref(d.instrument_id);
let activeChart = null;
export function updateChartRoute(r) {
  if (!activeChart || activeChart.id !== r.id || activeChart.name !== r.name || !$("#chart-range")) return false;
  activeChart.update(r);
  return true;
}
export function stockOverview(d, r) {
  return `<section class="panel market-chart-panel"><div class="chart-header"><h2>K 线与成交量</h2><span class="tag">真实 OHLC · 非复权</span></div><div class="candle-toolbar"><nav class="route-tabs" aria-label="K线周期">${[
    ["day", "日K"],
    ["week", "周K"],
    ["month", "月K"],
  ]
    .map(
      ([p, label]) =>
        `<a class="route-tab ${(r.params.get("period") || "day") === p ? "active" : ""}" data-chart-period="${p}" href="${chartHref(d, r)}?period=${p}&range=${r.params.get("range") || 120}" ${(r.params.get("period") || "day") === p ? 'aria-current="true"' : ""}>${label}</a>`,
    )
    .join(
      "",
    )}</nav><label for="chart-range">显示根数</label><select class="field" id="chart-range"><option value="60">60</option><option value="120">120</option><option value="250">250</option></select><div class="ma-legend">${Object.entries(
    maColors,
  )
    .map(([n, color]) => `<span style="color:${color}">MA${n}</span>`)
    .join(
      "",
    )}<span class="candle-up" data-market-legend="up">${document.documentElement.dataset.marketPalette === "us" ? "绿涨" : "红涨"}</span><span class="candle-down" data-market-legend="down">${document.documentElement.dataset.marketPalette === "us" ? "红跌" : "绿跌"}</span></div></div><div class="candle-readout" id="candle-readout" aria-live="off"></div><div class="candle-area" id="candle-area"></div><div class="history-range" id="history-range"></div><div class="table-footnote">${esc(d.bars_source || "暂无日线来源")} · 截至 ${esc(d.bars.at(-1)?.bar_time || "暂无")} · 周/月K由已缓存日线聚合。均线使用完整可用样本计算；停牌日不补K线。</div></section><div class="stock-overview-grid section-gap"><section class="panel"><div class="panel-header"><h2>最新盘口与估值</h2><span class="tag">来源原始字段</span></div><div id="stock-snapshot">${loading("正在查询盘口与估值…")}</div></section><section class="panel"><div class="panel-header"><h2>技术与风险指标</h2></div><div class="panel-body"><div class="metrics-list">${[
    ["20日均线", number(d.daily_metrics?.sma_20)],
    [
      d.index ? "60日均线" : "50日均线",
      number(
        d.index ? d.analysis.moving_averages["60"] : d.daily_metrics?.sma_50,
      ),
    ],
    [
      "区间涨跌",
      d.daily_metrics?.return_over_window == null
        ? "—"
        : percent(d.daily_metrics.return_over_window * 100),
    ],
    [
      "20日年化波动",
      d.daily_metrics?.annualized_volatility_20d == null
        ? "—"
        : number(d.daily_metrics.annualized_volatility_20d * 100) + "%",
    ],
    [
      "区间最大回撤",
      d.daily_metrics?.max_drawdown_in_window == null
        ? "—"
        : percent(d.daily_metrics.max_drawdown_in_window * 100),
    ],
    ["样本截止", esc(d.daily_metrics?.last_bar || "暂无")],
  ]
    .map(
      ([label, value]) =>
        `<div class="metric-line"><span>${label}</span><strong class="mono">${value}</strong></div>`,
    )
    .join(
      "",
    )}</div><p class="field-help">指标样本 ${esc(d.daily_metrics?.first_bar || "暂无")} 至 ${esc(d.daily_metrics?.last_bar || "暂无")}，共 ${number(d.daily_metrics?.observations, 0)} 根日线，独立于图表显示区间。非复权数据受除权除息影响，历史表现不代表未来。</p></div></section></div><div class="stock-source-links section-gap" id="stock-reference-links"></div>`;
}
function safeLink(value) {
  try {
    const url = new URL(String(value));
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}
function cell(value) {
  const link = safeLink(value);
  return link
    ? `<a class="text-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a>`
    : esc(
        value == null
          ? "—"
          : typeof value === "number"
            ? number(value, 4)
            : value,
      );
}
export function sectionMarkup(section) {
  if (!section)
    return empty("资料尚未返回", "可以重新请求或打开来源查询链接。");
  const rows = section.rows || [];
  const state = `<div class="dossier-status"><span class="tag ${["stale", "error", "partial"].includes(section.state) ? "amber" : ""}">${stateNames[section.state] || esc(section.state)}</span><span>${esc(section.source || "暂无数据来源")} · 接收 ${time(section.received_at)}${section.source_time ? " · 来源时间 " + time(section.source_time) : ""}</span></div>`;
  let body = "";
  if (rows.length) {
    if (rows.every((row) => "item" in row && "value" in row)) {
      body = `<div class="snapshot-grid">${rows.map((row) => `<div class="snapshot-item"><span>${esc(row.item)}</span><strong>${cell(row.value)}</strong></div>`).join("")}</div>`;
    } else if (section.section === "profile") {
      body = rows
        .map(
          (row) =>
            `<div class="company-profile">${Object.entries(row)
              .map(
                ([key, value]) =>
                  `<div><dt>${esc(key)}</dt><dd>${cell(value)}</dd></div>`,
              )
              .join("")}</div>`,
        )
        .join("");
    } else {
      const keys = [...new Set(rows.flatMap(Object.keys))];
      body = `<div class="table-scroll"><table class="data-table dossier-table"><thead><tr>${keys.map((key) => `<th>${esc(key)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${keys.map((key) => `<td>${cell(row[key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }
  } else
    body = empty(
      stateNames[section.state] || "暂无资料",
      section.error || section.unit_note || "请查看原始资料链接。",
    );
  return `${state}${section.error && rows.length ? `<div class="alert">${esc(section.error)}</div>` : ""}${body}<div class="table-footnote">${esc(section.unit_note || "")} ${esc(section.note || "")}</div>`;
}
export async function dossierTab(
  id,
  tab,
  signal,
  params = new URLSearchParams(),
) {
  const variants = {
    profile: [
      ["profile", "公司概况"],
      ["business", "主营构成"],
    ],
    financials: [
      ["financials", "财务摘要"],
      ["income", "利润表"],
      ["balance", "资产负债表"],
      ["cashflow", "现金流量表"],
      ["dividends", "分红"],
    ],
    ownership: [
      ["ownership", "股东户数"],
      ["holders", "十大股东"],
    ],
    flow: [["flow", "资金流向"]],
    news: [
      ["announcements", "公告"],
      ["news", "新闻"],
      ["reports", "机构研报目录"],
    ],
  };
  const options = variants[tab] || variants.profile;
  const selected = options.some(([key]) => key === params.get("dataset"))
    ? params.get("dataset")
    : options[0][0];
  const sections = [selected];
  const tabs = `<nav class="route-tabs" aria-label="资料类别">${options.map(([key, label]) => `<a class="route-tab ${key === selected ? "active" : ""}" href="${stockHref(id)}?tab=${tab}&dataset=${key}" ${key === selected ? 'aria-current="page"' : ""}>${label}</a>`).join("")}</nav>`;
  const result = await request(
    `/workspace/instruments/${encodeURIComponent(id)}/dossier?sections=${sections.join(",")}`,
    { signal, timeout: 23000 },
  );
  return `${tabs}<div class="actions section-gap"><button class="button primary" data-action="ask" data-question="请分析 ${esc(id)} 的${esc(labels[selected])}，使用个股资料工具查询相应分项；若分析财务则核对利润表、资产负债表和现金流量表的同一报告期，列出证据和风险。">${icon("spark")}让 Agent 分析这份资料</button></div>${sections.map((section) => `<section class="panel section-gap"><div class="panel-header"><h2>${labels[section]}</h2><button class="button small" type="button" data-refresh-dossier="${section}">${icon("refresh")}重新获取</button></div><div id="dossier-${section}">${sectionMarkup(result.sections[section])}</div></section>`).join("")}${sourceLinks(result.links)}`;
}
function sourceLinks(links) {
  return `<section class="source-links"><strong>原始资料与查询</strong>${links.map((link) => `<a class="button small ghost" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${esc(link.label)} ↗</a>`).join("")}<p class="field-help">外部链接由你直接打开，部分来源可能要求登录；页面资料缺失不会以推断补齐。</p></section>`;
}
export function mountStock(d, r, signal) {
  const rangeSelect = $("#chart-range");
  activeChart = null;
  if (rangeSelect) {
    let period, all, range, start, end;
    const draw = () => {
      const area = $("#candle-area");
      if (!area) return;
      if (!all.length) {
        area.innerHTML = empty(
          "还没有可用的 OHLC 日线",
          "点击“拉取日线”后展示真实K线。",
        );
        $("#candle-readout").textContent = "";
        return;
      }
      area.innerHTML = chartSVG(all, start, end);
      $("#candle-readout").innerHTML = sampleInfo(all[end - 1], all, end - 1);
      let selected = end - start - 1;
      const inspect = (i) => {
        selected = Math.max(0, Math.min(end - start - 1, i));
        $("#candle-readout").innerHTML = sampleInfo(
          all[start + selected],
          all,
          start + selected,
        );
        const x = 66 + ((986 - 66) / (end - start)) * (selected + 0.5);
        $("#chart-crosshair").setAttribute("visibility", "visible");
        $("#chart-crosshair-x").setAttribute("x1", x);
        $("#chart-crosshair-x").setAttribute("x2", x);
      };
      const svg = area.querySelector("svg");
      svg.onpointermove = (e) => {
        const hit = e.target.closest("[data-hit]");
        if (hit) inspect(Number(hit.dataset.hit));
      };
      svg.onkeydown = (e) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          inspect(
            e.key === "Home"
              ? 0
              : e.key === "End"
                ? end - start - 1
                : selected + (e.key === "ArrowLeft" ? -1 : 1),
          );
        }
      };
      svg.onfocus = () => inspect(selected);
    };
    const update = (route) => {
      period = ["day", "week", "month"].includes(route.params.get("period")) ? route.params.get("period") : "day";
      range = [60, 120, 250].includes(Number(route.params.get("range"))) ? Number(route.params.get("range")) : 120;
      all = aggregateBars(d.bars, period);
      start = Math.max(0, all.length - range);
      end = all.length;
      rangeSelect.value = String(range);
      for (const tab of document.querySelectorAll("[data-chart-period]")) {
        const selected = tab.dataset.chartPeriod === period;
        tab.classList.toggle("active", selected);
        if (selected) tab.setAttribute("aria-current", "true");
        else tab.removeAttribute("aria-current");
        tab.href = `${chartHref(d, r)}?period=${tab.dataset.chartPeriod}&range=${range}`;
      }
      draw();
      const history = $("#history-range");
      if (all.length > range) {
        history.innerHTML = `<label for="chart-history">历史区间</label><input type="range" id="chart-history" min="0" max="${all.length - range}" value="${start}" step="1" /><span class="muted">拖动或使用方向键查看历史K线</span>`;
        $("#chart-history").oninput = (e) => {
          start = Number(e.target.value);
          end = Math.min(all.length, start + range);
          draw();
        };
      } else {
        history.innerHTML = `<span class="field-help">当前有 ${all.length} 根${period === "day" ? "日" : period === "week" ? "周" : "月"}K线；可拉取更多日线扩展样本。</span>`;
      }
    };
    activeChart = { id: r.id, name: d.index ? "indices" : "stocks", update };
    rangeSelect.onchange = (e) => {
      location.hash = `${chartHref(d, r).slice(1)}?period=${period}&range=${e.target.value}`;
    };
    document.querySelectorAll("[data-chart-period]").forEach((tab) => {
      tab.onclick = (e) => {
        e.preventDefault();
        location.hash = `${chartHref(d, r).slice(1)}?period=${tab.dataset.chartPeriod}&range=${range}`;
      };
    });
    update(r);
    if (d.index) {
      $("#stock-snapshot").innerHTML =
        `<p class="field-help">指数点位用于观察市场结构，不具有个股盘口与估值资料。${esc(d.note || "")}</p>`;
    }
    if (!d.index)
      request(
        `/workspace/instruments/${encodeURIComponent(d.instrument_id)}/dossier?sections=snapshot`,
        { signal, timeout: 23000 },
      )
        .then((result) => {
          if (signal.aborted) return;
          $("#stock-snapshot").innerHTML = sectionMarkup(
            result.sections.snapshot,
          );
          $("#stock-reference-links").innerHTML = sourceLinks(result.links);
        })
        .catch((error) => {
          if (!signal.aborted && $("#stock-snapshot"))
            $("#stock-snapshot").innerHTML = empty(
              "盘口资料暂不可用",
              error.message,
            );
        });
  }
  for (const button of document.querySelectorAll("[data-refresh-dossier]"))
    button.onclick = async () => {
      button.disabled = true;
      const section = button.dataset.refreshDossier,
        holder = $("#dossier-" + section);
      try {
        const result = await request(
          `/workspace/instruments/${encodeURIComponent(d.instrument_id)}/dossier?sections=${section}&refresh=true`,
          { signal, timeout: 23000 },
        );
        if (!signal.aborted)
          holder.innerHTML = sectionMarkup(result.sections[section]);
      } catch (error) {
        if (!signal.aborted)
          holder.innerHTML = empty("请求未完成", error.message);
      } finally {
        button.disabled = false;
      }
    };
}
