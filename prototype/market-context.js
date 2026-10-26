import { request } from "./api.js";
import {
  esc,
  icon,
  number,
  percent,
  tone,
  time,
  empty,
  notify,
  sectorHref,
} from "./ui.js";
let timer = null;
const states = {
  available: "已有数据",
  partial: "部分可用",
  stale: "过期缓存",
  unavailable: "暂无数据",
  error: "来源不可用",
  pending: "正在采集",
  disabled: "采集关闭",
};
const phases = {
  improving: "相对改善",
  weakening: "相对转弱",
  persistent_leader: "多周期领先",
  mixed: "交错 / 震荡",
  insufficient: "数据不足",
};
const panel = (title, body) =>
  `<section class="panel section-gap"><div class="panel-header"><h2>${esc(title)}</h2></div><div class="panel-body">${body}</div></section>`;
function sources(rows = []) {
  return `<div class="provider-list">${rows.map((x) => `<div class="provider-item"><strong>${esc(x.source || "公共数据来源")}</strong> <span class="tag ${x.state === "available" ? "" : "amber"}">${states[x.state] || esc(x.state)}</span><p>发布 ${time(x.source_time)} · 接收 ${time(x.received_at)}</p>${x.error ? `<p>${esc(x.error)}</p>` : ""}</div>`).join("")}</div>`;
}
export function cleanupContext() {
  clearTimeout(timer);
  timer = null;
}
function newsRows(rows) {
  if (!rows.length)
    return empty("暂无匹配快讯", "数据源可能尚未返回；可换关键词或稍后刷新。");
  return rows
    .map(
      (x) =>
        `<article class="provider-item"><div class="actions"><span class="tag">${esc(x.source)}</span><span class="field-help">发布 ${time(x.published_at)} · 首次采集 ${time(x.first_seen_at)}</span></div><h3 class="section-gap">${esc(x.title || "财经快讯")}</h3><p>${esc(x.content)}</p>${x.matched_sectors?.length ? `<div class="actions section-gap">${x.matched_sectors.map((n) => `<a class="button small ghost" href="#/news?q=${encodeURIComponent(n)}">${esc(n)} · 关联候选</a>`).join("")}</div>` : ""}<div class="actions section-gap">${x.url ? `<a class="text-link" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">打开来源 ↗</a>` : ""}<button class="button small" data-action="ask" data-question="请分析这条新闻的潜在行业影响：${esc(x.title)}。发布时间 ${esc(x.published_at || "来源未提供")}，请先用新闻工具检索核实，区分事实、推断与风险，并结合央行流动性和板块轮动，不直接推导买卖。">${icon("spark")}分析行业影响</button></div></article>`,
    )
    .join("");
}
export async function renderNews(r, signal, ui) {
  const query = r.params.get("q") || "";
  const d = await request(
    "/research/news?limit=30&query=" + encodeURIComponent(query),
    { signal, timeout: 25000 },
  );
  if (signal.aborted) return;
  ui.setPage(
    ui.page(
      ui.heading(
        "新闻与流动性",
        "新闻事件、政策环境和行业影响进入同一条研究链路。",
        `<a class="button" href="#/liquidity">央行逆回购 →</a><button class="button" data-action="context-refresh" data-kind="news">${icon("refresh")}立即采集</button>`,
      ) +
        `<form id="news-filter-form" class="filter-bar" data-draft><label class="field-label" for="news-query">行业 / 关键词</label><input id="news-query" class="field" name="q" value="${esc(query)}" maxlength="80" placeholder="例如 半导体、算力、逆回购"><button type="submit" class="button">筛选快讯</button></form><p class="field-help">服务每60秒尝试采集，页面每60秒更新列表；公共源不保证秒级实时。关键词只标关联候选，不确认因果。</p><div class="section-gap" id="news-source-state">${sources(d.sources)}</div>${panel("最近已采集快讯 · 最多30条", `<div id="market-news-list">${newsRows(d.rows)}</div>`)}<div id="context-refresh-error" class="form-error" role="status"></div>`,
    ),
  );
  const update = async () => {
    if (signal.aborted) return;
    try {
      const latest = await request(
        "/research/news?limit=30&query=" + encodeURIComponent(query),
        { signal, timeout: 25000 },
      );
      if (signal.aborted) return;
      document.querySelector("#market-news-list").innerHTML = newsRows(
        latest.rows,
      );
      document.querySelector("#news-source-state").innerHTML = sources(
        latest.sources,
      );
      document.querySelector("#context-refresh-error").textContent = "";
    } catch (e) {
      if (!signal.aborted)
        document.querySelector("#context-refresh-error").textContent =
          "快讯更新未完成：" + e.message;
    }
    if (!signal.aborted) timer = setTimeout(update, 60000);
  };
  timer = setTimeout(update, 60000);
}
export async function renderLiquidity(r, signal, ui) {
  const d = await request("/research/liquidity", { signal, timeout: 25000 });
  if (signal.aborted) return;
  ui.setPage(
    ui.page(
      ui.heading(
        "央行流动性",
        "按公告核实逆回购操作，观察市场环境。",
        `<button class="button" data-action="context-refresh" data-kind="liquidity">${icon("refresh")}重新采集</button><button class="button primary" data-action="ask" data-question="请读取央行最新逆回购公告，按期限说明投放、操作利率与数据缺口，不能在缺到期额时推算净投放，再结合指数与板块轮动分析可能的市场影响和反方证据。">${icon("spark")}分析流动性与轮动</button>`,
      ) +
        sources([d]) +
        `<p class="field-help section-gap">${esc(d.note || "")}</p>` +
        (d.rows.length
          ? d.rows
              .map((x) =>
                panel(
                  x.title,
                  `<p class="field-help">来源发布时间 ${time(x.published_at)}</p><div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>期限</th><th>操作量（亿元）</th><th>操作利率</th><th>到期量 / 净投放</th></tr></thead><tbody>${x.operations.map((o) => `<tr><td>${esc(o.tenor)}</td><td class="mono">${number(o.amount_yi)}</td><td>${o.rate_percent == null ? "未披露" : number(o.rate_percent) + "%"}</td><td>数据不足</td></tr>`).join("")}</tbody></table></div>${!x.operations.length ? '<p class="field-help">结构化字段未提取，请以公告原文为准。</p>' : ""}<details class="section-gap"><summary>查看采集原文</summary><p class="field-help">${esc(x.excerpt)}</p></details><a class="text-link section-gap" href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">央行公告原文 ↗</a>`,
                ),
              )
              .join("")
          : panel(
              "公开市场操作",
              empty(
                "公告尚未返回",
                "可稍后重试或打开央行公告目录。",
                `<a class="button" href="https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/index.html" target="_blank" rel="noopener noreferrer">央行公告目录 ↗</a>`,
              ),
            )),
    ),
  );
}
export function rotationMarkup(d, r) {
  const options = {
    all: "全部行业",
    persistent_leader: "多周期领先",
    improving: "相对改善",
    weakening: "相对转弱",
    insufficient: "数据不足",
  };
  const view = Object.hasOwn(options, r.params.get("phase")) ? r.params.get("phase") : "all";
  const filtered = (d.rows || []).filter((x) => view === "all" || x.phase === view);
  const page = Math.min(
    Math.max(1, Math.ceil(filtered.length / 20)),
    Math.max(1, parseInt(r.params.get("page"), 10) || 1),
  );
  const rows = filtered.slice((page - 1) * 20, page * 20);
  const tabs = Object.entries(options).map(([key, label]) =>
    `<a class="route-tab ${view === key ? "active" : ""}" href="#/sectors?phase=${key}" ${view === key ? 'aria-current="page"' : ""}>${label}</a>`,
  ).join("");
  const tableRows = rows.map((x) => `<tr><td><a class="stock-link" href="${sectorHref(x.name)}">${esc(x.name)}</a><small>${phases[x.phase] || esc(x.phase)}</small></td>${["今日", "5日", "10日"].map((w) => `<td class="mono ${tone(x.windows[w].return_percent)}">${percent(x.windows[w].return_percent)}<small>${x.windows[w].rank == null ? "无共同集合排名" : "第" + x.windows[w].rank + "名"}</small></td>`).join("")}<td class="mono ${tone(x.windows["今日"].main_net_yuan)}">${x.windows["今日"].main_net_yuan == null ? "—" : number(x.windows["今日"].main_net_yuan / 1e8) + "亿元"}</td><td>${x.rank_improvement == null ? "—" : (x.rank_improvement > 0 ? "+" : "") + x.rank_improvement}</td><td>${x.previous_capture_rank_change == null ? "尚无可比快照" : (x.previous_capture_rank_change > 0 ? "+" : "") + x.previous_capture_rank_change}</td></tr>`).join("");
  const table = rows.length
    ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>行业 / 阶段</th><th>今日涨跌 / 排名</th><th>5日涨跌 / 排名</th><th>10日涨跌 / 排名</th><th>今日主力净额</th><th>跨窗口改善</th><th>较上次采集日</th></tr></thead><tbody>${tableRows}</tbody></table></div>`
    : empty("暂无轮动样本", "部分来源尚未返回，不补造排名。");
  const pager = `<div class="table-footer"><span>${filtered.length} 个行业 · 第 ${page} 页</span><div class="pager">${page > 1 ? `<a class="button small" href="#/sectors?phase=${encodeURIComponent(view)}&page=${page - 1}">上一页</a>` : ""}${page * 20 < filtered.length ? `<a class="button small" href="#/sectors?phase=${encodeURIComponent(view)}&page=${page + 1}">下一页</a>` : ""}</div></div>`;
  return `<section class="sector-research-section section-gap" aria-labelledby="rotation-title"><div class="sector-section-heading"><div><h2 id="rotation-title">板块轮动观察</h2><p>今日、5 日和 10 日相对强弱与资金变化；点击行业查看成分股及资金明细。</p></div></div><nav class="route-tabs section-gap" aria-label="轮动阶段">${tabs}</nav><p class="field-help section-gap">共同板块 ${number(d.common_universe, 0)} 个 · ${esc(d.method || "来源尚无可比样本")}</p>${panel("相对强弱与资金", table + pager)}<p class="field-help section-gap">${esc(d.note || "")}${d.previous_capture_date ? " 上次采集日期 " + esc(d.previous_capture_date) + "。" : ""}</p>${panel("各周期来源状态", sources(d.sources))}${panel("最近采集日领先行业", d.history?.length ? d.history.map((x) => `<div class="metric-line"><span>${esc(x.capture_date)}</span><strong>${esc(x.leaders.join(" / "))}</strong></div>`).join("") : empty("还没有历史采集快照", "采集成功后逐日积累，不伪造过去的板块轮动。"))}</section>`;
}
export async function handleContextSubmit(form, values) {
  if (form.id !== "news-filter-form") return false;
  location.hash = "/news?q=" + encodeURIComponent(values.q.trim());
  return true;
}
export async function handleContextAction(button, ui) {
  if (button.dataset.action !== "context-refresh") return false;
  const path = {
    news: "/research/news",
    liquidity: "/research/liquidity",
    rotation: "/research/rotation",
  }[button.dataset.kind];
  if (!path) return true;
  await ui.busy(button, async () => {
    try {
      await request(path + "?refresh=true", {
        signal: ui.signal(),
        timeout: 25000,
      });
      notify("已请求采集，排队中的来源稍后刷新查看。");
      await ui.renderRoute();
    } catch (e) {
      notify(e.message, "error");
    }
  });
  return true;
}
