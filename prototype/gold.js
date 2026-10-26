import { request } from "./api.js";
import { aggregateBars, chartSVG } from "./stock.js";
import { esc, money, number, percent, time, tone, empty, icon } from "./ui.js";

const INSTRUMENT = "GOLD:Au99.99";
const goldState = { bars: [] };
const fmtDate = (value) => value ? String(value).slice(0, 10) : "—";
const quoteTime = (value) => {
  if (!value) return time(value);
  const parsed = new Date(value);
  return !Number.isNaN(parsed.getTime()) && parsed.getTime() > Date.now() + 5 * 60 * 1000
    ? `上游时间超前 · ${time(value)}`
    : time(value);
};
const sma = (bars, count) => bars.length >= count
  ? bars.slice(-count).reduce((sum, row) => sum + Number(row.close), 0) / count
  : null;
function historyNote(bars) {
  if (!bars.length) return "日线尚未取得";
  const close = Number(bars.at(-1).close);
  const returns = (count) => bars.length > count ? (close / Number(bars.at(-1 - count).close) - 1) * 100 : null;
  const r20 = returns(20), r60 = returns(60), ma20 = sma(bars, 20), ma60 = sma(bars, 60);
  const trend = ma20 == null ? "样本不足20根，暂不计算短期均线" : `最新收盘${close >= ma20 ? "高于" : "低于"}20日均线 ${number(ma20)} 元/克`;
  const longTrend = ma60 == null ? "60日均线样本不足" : `，${close >= ma60 ? "高于" : "低于"}60日均线 ${number(ma60)} 元/克`;
  const changes = [r20 == null ? "近20根日线样本不足" : `近20根日线 ${percent(r20)}`, r60 == null ? "近60根日线样本不足" : `近60根日线 ${percent(r60)}`];
  return `${trend}${longTrend}；${changes.join("；")}。以上为已取得日线的历史描述，不构成价格预测。`;
}
function chartMarkup(bars, count = 120) {
  const sampled = aggregateBars(bars, "day");
  if (!sampled.length) return empty("暂无黄金日线", "可点击“采集历史日线”从上海黄金交易所来源获取日线。", `<button class="button small" data-action="gold-history">采集历史日线</button>`);
  const start = Math.max(0, sampled.length - count);
  return `<div class="gold-chart-scroll">${chartSVG(sampled, start, sampled.length)}</div><p class="field-help">日线 ${fmtDate(sampled[0].bar_time)} 至 ${fmtDate(sampled.at(-1).bar_time)} · ${sampled.length} 根 · ${esc(sampled.at(-1).source || "上金所历史数据")}</p>`;
}
function newsMarkup(rows) {
  const relevant = rows.filter((row) => /黄金|金价|贵金属|避险|央行购金|黄金ETF|金银/i.test(`${row.title || ""} ${row.content || ""}`)).slice(0, 15);
  if (!relevant.length) return empty("暂无匹配的黄金相关新闻", "新闻列表仅展示已采集内容；可到新闻与流动性页面查看来源状态。", `<a class="button small" href="#/news?q=${encodeURIComponent("黄金")}">查看黄金相关新闻</a>`);
  return `<div class="gold-news-list">${relevant.map((row) => `<article class="gold-news-item"><div class="gold-news-meta"><span class="tag">${esc(row.source || "新闻来源")}</span><span>${time(row.published_at)}</span></div><h3>${row.url ? `<a href="${esc(row.url)}" target="_blank" rel="noopener noreferrer">${esc(row.title || "黄金市场快讯")} ↗</a>` : esc(row.title || "黄金市场快讯")}</h3><p>${esc(row.content || "来源未提供摘要")}</p></article>`).join("")}</div>`;
}
const getRange = () => Math.max(30, Math.min(250, Number(document.querySelector("#gold-range")?.value) || 120));
document.addEventListener("change", (event) => {
  if (event.target?.id !== "gold-range") return;
  const chart = document.querySelector("#gold-chart");
  if (chart) chart.innerHTML = chartMarkup(goldState.bars, getRange());
});

export async function renderGold(_route, signal, ui) {
  const [quotes, initialBars, news] = await Promise.allSettled([
    request("/quotes?market=GOLD&limit=20", { signal, timeout: 25000 }),
    request(`/bars?instrument_id=${encodeURIComponent(INSTRUMENT)}&interval=1d&start=${new Date(Date.now() - 5 * 365 * 86400000).toISOString().slice(0, 10)}&end=${new Date().toISOString().slice(0, 10)}`, { signal }),
    request("/research/news?query=%E9%BB%84%E9%87%91&limit=100", { signal, timeout: 25000 }),
  ]);
  if (signal.aborted) return;
  let bars = initialBars.status === "fulfilled" ? initialBars.value.bars || [] : [];
  let historyError = initialBars.status === "rejected" ? initialBars.reason.message : "";
  if (!bars.length && !historyError) {
    try {
      await request(`/bars/pull?instrument_id=${encodeURIComponent(INSTRUMENT)}&start=${new Date(Date.now() - 5 * 365 * 86400000).toISOString().slice(0, 10)}&end=${new Date().toISOString().slice(0, 10)}&interval=1d`, { method: "POST", signal, timeout: 25000 });
      const stored = await request(`/bars?instrument_id=${encodeURIComponent(INSTRUMENT)}&interval=1d&start=${new Date(Date.now() - 5 * 365 * 86400000).toISOString().slice(0, 10)}&end=${new Date().toISOString().slice(0, 10)}`, { signal });
      bars = stored.bars || [];
    } catch (error) {
      if (signal.aborted) return;
      historyError = error.message;
    }
  }
  goldState.bars = bars;
  const quote = quotes.status === "fulfilled" ? quotes.value.quotes?.find((row) => row.symbol === "Au99.99") || quotes.value.quotes?.[0] : null;
  const newsData = news.status === "fulfilled" ? news.value : { rows: [], sources: [], state: "unavailable" };
  ui.setPage(ui.page(
    ui.heading("黄金行情", "上海黄金交易所 Au99.99 现货报价、历史日线与相关新闻。页面每分钟同步本机行情缓存；上游更新频率依公开数据源而定，不代表交易所实时推送。", `<button class="button" data-action="refresh-market" data-market="GOLD">${icon("refresh")}刷新报价</button><button class="button" data-action="gold-history">采集历史日线</button><button class="button primary" data-action="ask" data-question="请基于黄金行情页面显示的上金所 Au99.99 报价、历史日线与相关新闻，分析黄金市场。先核实每条数据的来源和时间，区分事实与推断，说明趋势依据、可能催化因素和反方风险；没有证据的结论明确标注数据不足，不提供确定性预测。">${icon("spark")}生成市场分析</button>`)
    + `<section class="panel gold-quote-panel"><div class="gold-quote-main"><span class="field-help">上海黄金交易所 · Au99.99 · 人民币/克</span><strong class="gold-price mono" id="gold-live-price">${quote ? money(quote.last, "CNY") : "暂无报价"}</strong><span class="gold-change mono ${tone(quote?.change_percent)}" id="gold-live-change">${quote?.change_percent == null ? "涨跌幅未提供" : percent(quote.change_percent)}</span></div><div class="gold-quote-facts"><div><small>行情时间</small><strong id="gold-live-time">${quoteTime(quote?.exchange_time)}</strong></div><div><small>本机接收</small><strong id="gold-live-received">${time(quote?.received_at)}</strong></div><div><small>行情来源</small><strong id="gold-live-provider">${esc(quote?.provider || "暂无来源信息")}</strong></div></div>${!quote ? `<p class="form-error">${quotes.status === "rejected" ? esc(quotes.reason.message) : "来源尚未返回 Au99.99 报价；可尝试刷新。"}</p>` : ""}</section>`
    + `<section class="panel section-gap"><div class="panel-header gold-chart-header"><div><h2>黄金日K</h2><p>真实 OHLC · 日线历史</p></div><label class="gold-range-label" for="gold-range">显示根数<select class="field" id="gold-range"><option value="60">60</option><option value="120" selected>120</option><option value="250">250</option></select></label></div><div class="panel-body"><div id="gold-chart">${chartMarkup(bars)}</div>${historyError ? `<p class="form-error">历史日线采集失败：${esc(historyError)}</p>` : ""}</div></section>`
    + `<section class="panel section-gap"><div class="panel-header"><div><h2>行情观察</h2><p>根据最近已采集日线计算，不以实时现货价替代历史收盘。</p></div></div><div class="panel-body"><p class="gold-analysis-copy">${esc(historyNote(bars))}</p><div class="gold-stats"><div><small>日线截止</small><strong>${fmtDate(bars.at(-1)?.bar_time)}</strong></div><div><small>20日均线</small><strong>${sma(bars, 20) == null ? "样本不足" : `${number(sma(bars, 20))} 元/克`}</strong></div><div><small>60日均线</small><strong>${sma(bars, 60) == null ? "样本不足" : `${number(sma(bars, 60))} 元/克`}</strong></div></div></div></section>`
    + `<section class="panel section-gap"><div class="panel-header"><div><h2>黄金相关新闻</h2><p>从新闻采集库按“黄金”检索 · ${esc(newsData.state || "未知状态")}</p></div><a class="text-link" href="#/news?q=${encodeURIComponent("黄金")}">新闻与流动性 ↗</a></div><div class="panel-body">${newsMarkup(newsData.rows || [])}<p class="field-help section-gap">${esc(newsData.note || "新闻来源可能延迟；列表仅代表本机已采集记录。")}</p>${(newsData.sources || []).map((source) => `<p class="field-help">${esc(source.source || "来源")} · ${esc(source.state || "未知状态")} · 发布 ${time(source.source_time)} / 接收 ${time(source.received_at)}</p>`).join("")}</div></section>`
  ));
  let timer;
  signal.addEventListener("abort", () => clearTimeout(timer), { once: true });
  const refreshQuote = async () => {
    if (signal.aborted) return;
    if (document.visibilityState === "visible") {
      try {
        const latest = await request("/quotes?market=GOLD&limit=20", { signal, timeout: 15000 });
        const row = latest.quotes?.find((item) => item.symbol === "Au99.99") || latest.quotes?.[0];
        if (row && !signal.aborted && document.querySelector("#gold-live-price")) {
          document.querySelector("#gold-live-price").textContent = money(row.last, "CNY");
          const change = document.querySelector("#gold-live-change");
          change.textContent = row.change_percent == null ? "涨跌幅未提供" : percent(row.change_percent);
          change.className = `gold-change mono ${tone(row.change_percent)}`;
          document.querySelector("#gold-live-time").textContent = quoteTime(row.exchange_time);
          document.querySelector("#gold-live-received").textContent = time(row.received_at);
          document.querySelector("#gold-live-provider").textContent = row.provider || "来源未提供";
        }
      } catch (_error) {
        // Retain the last known quote and retry on the next visible-page interval.
      }
    }
    if (!signal.aborted) timer = setTimeout(refreshQuote, 60000);
  };
  timer = setTimeout(refreshQuote, 60000);
}

export async function handleGoldAction(button, rerender) {
  if (button.dataset.action !== "gold-history") return false;
  button.disabled = true;
  try {
    const end = new Date().toISOString().slice(0, 10);
    const start = new Date(Date.now() - 5 * 365 * 86400000).toISOString().slice(0, 10);
    await request(`/bars/pull?instrument_id=${encodeURIComponent(INSTRUMENT)}&start=${start}&end=${end}&interval=1d`, { method: "POST", timeout: 30000 });
    rerender();
  } catch (error) {
    const node = document.querySelector("#gold-chart");
    if (node) node.insertAdjacentHTML("afterend", `<p class="form-error">历史日线采集失败：${esc(error.message)}</p>`);
  } finally {
    button.disabled = false;
  }
  return true;
}
