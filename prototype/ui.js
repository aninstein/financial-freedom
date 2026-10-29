export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
// Keep existing nodes and their focus when a URL filter changes within one page.
export function patchContent(target, html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  const patch = (current, next) => {
    if (current.isEqualNode(next)) return;
    if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName) {
      current.replaceWith(next.cloneNode(true));
      return;
    }
    if (current.nodeType === Node.TEXT_NODE || current.nodeType === Node.COMMENT_NODE) {
      current.nodeValue = next.nodeValue;
      return;
    }
    const focused = current === document.activeElement;
    for (const { name } of [...current.attributes])
      if (!next.hasAttribute(name)) current.removeAttribute(name);
    for (const { name, value } of [...next.attributes])
      if (current.getAttribute(name) !== value) current.setAttribute(name, value);
    patchChildren(current, next);
    if (current instanceof HTMLInputElement && current.type !== "file") {
      if (current.type === "checkbox" || current.type === "radio") current.checked = next.checked;
      else if (!focused) current.value = next.value;
    } else if (current instanceof HTMLTextAreaElement && !focused) current.value = next.value;
    else if (current instanceof HTMLSelectElement && !focused) current.value = next.value;
  };
  const patchChildren = (current, next) => {
    let index = 0;
    while (index < next.childNodes.length) {
      const oldChild = current.childNodes[index];
      if (!oldChild) current.appendChild(next.childNodes[index].cloneNode(true));
      else patch(oldChild, next.childNodes[index]);
      index++;
    }
    while (current.childNodes.length > next.childNodes.length) current.lastChild.remove();
  };
  patchChildren(target, template.content);
}
const paths = {
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12ZM9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0",
  shield: "M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4ZM8 12l3 3 5-6",
  spark: "m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3L12 3Z",
  chat: "M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 4V6a2 2 0 0 1 2-2Z",
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  star: "m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z",
  chart: "M4 3v17h17M7 14l4-4 4 2 5-7",
  globe: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20",
  candles: "M5 3v18M3 7h4v6H3zM12 2v20M10 11h4v7h-4zM19 4v16M17 6h4v5h-4z",
  bank: "m3 10 9-7 9 7M5 10h14M6 10v9M10 10v9M14 10v9M18 10v9M4 21h16M3 19h18",
  coins: "M12 4c-4.4 0-8 1.6-8 3.5S7.6 11 12 11s8-1.6 8-3.5S16.4 4 12 4ZM4 8v4c0 1.9 3.6 3.5 8 3.5 1.5 0 2.9-.2 4.1-.6M4 12v4c0 1.9 3.6 3.5 8 3.5h1M20 12.5c0-1.7-2.5-3-5.5-3S9 10.8 9 12.5s2.5 3 5.5 3 5.5-1.3 5.5-3ZM9 12.5v4c0 1.7 2.5 3 5.5 3s5.5-1.3 5.5-3v-4",
  layers: "m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5",
  calendar:
    "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2ZM7 14h3M14 14h3M7 18h3",
  flask: "M9 3h6M10 3v6L4 19a1 1 0 0 0 1 2h14a1 1 0 0 0 1-2L14 9V3M8 14h8",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6ZM14 2v6h6M8 13h8M8 17h6",
  wallet: "M3 6h16v14H3zM3 6V4h14M15 11h6v5h-6z",
  orders: "M6 3h12v18l-3-2-3 2-3-2-3 2V3ZM9 7h6M9 11h6",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4",
  plus: "M12 5v14M5 12h14",
  search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  up: "M12 19V5M5 12l7-7 7 7",
  back: "M19 12H5M11 6l-6 6 6 6",
  refresh:
    "M20 7v5h-5M4 17v-5h5M5.1 8a7 7 0 0 1 11.5-3L20 8M4 16l3.4 3A7 7 0 0 0 19 16",
  menu: "M4 6h16M4 12h16M4 18h16",
  clock: "M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  check: "m5 12 4 4L19 6",
  copy: "M9 9h12v12H9zM15 9V3H3v12h6",
  paperclip: "m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2",
  close: "m6 6 12 12M6 18 18 6",
  link: "M10 13a5 5 0 0 0 7 0l4-4a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-4 4a5 5 0 0 0 7 7l2-2",
};
export function icon(name, cls = "") {
  return `<svg class="${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name] || paths.spark}"/></svg>`;
}
export function brandMark(cls = "") {
  return `<img class="brand-logo ${cls}" src="/assets/finfreedom-mark.svg" alt="" />`;
}
export const markets = {
  CN: "A 股 / 创业板 / 科创板",
  HK: "港股",
  US: "美股",
  FUND: "基金 / ETF",
  GOLD: "黄金",
};
export const phases = {
  open: "交易中",
  closed: "已收盘",
  holiday: "非交易日",
  pre_market: "盘前",
  preopen: "盘前",
  break: "午间休市",
  unknown: "状态未知",
};
export function number(v, d = 2) {
  return v == null || !Number.isFinite(Number(v))
    ? "—"
    : new Intl.NumberFormat("zh-CN", {
        maximumFractionDigits: d,
        minimumFractionDigits: d,
      }).format(Number(v));
}
export function money(v, currency = "CNY") {
  return v == null
    ? "—"
    : new Intl.NumberFormat("zh-CN", {
        style: "currency",
        currency,
        maximumFractionDigits: Number(v) < 2 ? 4 : 2,
      }).format(Number(v));
}
export const percent = (v) =>
  v == null ? "—" : `${Number(v) > 0 ? "+" : ""}${number(v)}%`;
export const tone = (v) =>
  v == null
    ? "muted"
    : Number(v) > 0
      ? "market-up"
      : Number(v) < 0
        ? "market-down"
        : "muted";
export function time(v) {
  if (!v) return "来源未提供";
  const date = new Date(v);
  return Number.isNaN(date.getTime())
    ? esc(v)
    : date.toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Shanghai",
        hour12: false,
      });
}
export const stockHref = (id) => "#/stocks/" + encodeURIComponent(id);
export const sectorHref = (name) => "#/sectors/" + encodeURIComponent(name);
export function fresh(q) {
  const names = {
    realtime: "实时",
    delayed: "延迟行情",
    end_of_day: "日终 / 净值",
    stale: "已过期",
    unknown: "时效未知",
    unavailable: "暂不可用",
  };
  return `<span class="tag ${q?.freshness === "stale" ? "amber" : ""}">${names[q?.freshness] || "时效未知"}</span>`;
}
export function empty(title, body = "", action = "", symbol = "chart") {
  return `<div class="empty">${icon(symbol)}<strong>${esc(title)}</strong><p>${esc(body)}</p>${action}</div>`;
}
export const loading = (label = "正在读取数据…") =>
  `<div class="loading" role="status"><span class="spinner"></span>${esc(label)}</div>`;
export function errorPanel(error, action = "retry-route") {
  return `<div class="alert error" role="alert">${esc(error?.message || error)} <button class="button small ghost" data-action="${action}">重试</button></div>`;
}
export function stat(label, value, note = "") {
  return `<div class="stat"><div class="stat-label">${esc(label)}</div><div class="stat-value">${value}</div><div class="stat-note">${esc(note)}</div></div>`;
}
export function resultCards(cards = []) {
  return cards
    .map((card) => {
      if (card.kind === "context")
        return `<a class="result-card" href="#/${{ market_news: "news", macro_liquidity: "liquidity", sector_rotation: "sectors" }[card.context] || "chat"}"><div class="result-card-head"><strong>${esc(card.title)}</strong>${icon("arrow")}</div><div class="result-foot"><span>来源与数据状态</span><span>打开研究详情</span></div></a>`;
      if (card.kind === "index")
        return `<a class="result-card" href="#/indices/${encodeURIComponent(card.instrument_id)}"><div class="result-card-head"><strong>${esc(card.name)}</strong>${icon("arrow")}</div><div class="result-price">${number(card.last_close)}<small>点</small></div><div class="result-foot"><span>日线 ${esc(card.last_bar || "暂无")}</span><span>打开指数分析</span></div></a>`;
      if (card.kind === "fund")
        return `<a class="result-card" href="#/funds/${encodeURIComponent(card.code)}"><div class="result-card-head"><strong>${esc(card.name || card.code)}</strong>${icon("arrow")}</div><div class="result-price">${number(card.latest_nav?.nav, 4)}<small>单位净值</small></div><div class="result-foot"><span>${esc(card.latest_nav?.date || "暂无净值日期")}</span><span>打开基金分析</span></div></a>`;
      if (card.kind === "cycles")
        return `<a class="result-card" href="${card.instrument_id.startsWith("INDEX:") ? "#/indices/" + encodeURIComponent(card.instrument_id) : stockHref(card.instrument_id) + "?tab=cycles"}"><div class="result-card-head"><strong>${esc(card.instrument_id)} 历史周期</strong>${icon("arrow")}</div><div class="result-foot"><span>${esc(card.last_bar || "样本不足")}</span><span>查看样本统计</span></div></a>`;
      if (card.kind === "instrument")
        return `<a class="result-card" href="${stockHref(card.instrument_id)}"><div class="result-card-head"><strong>${esc(card.name || card.instrument_id)}</strong>${icon("arrow")}</div><div class="symbol">${esc(card.instrument_id)}</div><div class="result-price">${money(card.last, card.currency)}<small class="${tone(card.change_percent)}">${percent(card.change_percent)}</small></div><div class="result-foot"><span>查看个股详情</span><span>${esc((card.evidence_ids || []).join(" · "))}</span></div>${card.freshness || card.source ? `<div class="result-meta">${fresh(card)}${card.provider || card.source ? `<span>${esc(card.provider || card.source)}</span>` : ""}${card.exchange_time || card.as_of ? `<span>行情时点 ${esc(time(card.exchange_time || card.as_of))}</span>` : ""}${Number(card.known_delay_seconds) > 0 ? `<span>已知延迟 ${number(card.known_delay_seconds / 60, 0)} 分钟</span>` : ""}</div>` : ""}</a>`;
      if (card.kind === "sector")
        return `<a class="result-card" href="${sectorHref(card.name)}"><div class="result-card-head"><strong>${esc(card.name)}板块</strong>${icon("arrow")}</div><div class="result-price">${percent(card.summary?.["涨跌幅"])}</div><div class="result-foot"><span>${card.flow ? "含行业资金统计" : "资金数据待补充"}</span><span>打开板块详情</span></div></a>`;
      if (card.kind === "market")
        return `<a class="result-card" href="#/markets?market=${esc(card.market)}"><div class="result-card-head"><strong>${esc(markets[card.market] || card.market)} 市场</strong>${icon("arrow")}</div><div class="result-price">${number(card.advancers, 0)}<small>上涨 / ${number(card.decliners, 0)} 下跌</small></div><div class="result-foot"><span>${number(card.quote_count, 0)} 个缓存标的</span><span>查看市场</span></div></a>`;
      return "";
    })
    .join("");
}
function inline(value) {
  const s = String(value);
  const regex =
    /(\*\*[^*]+\*\*|~~[^~]+~~|`[^`]+`|\[[^\]]+\]\([^\s)]+\)|\[E\d+\]|\b(?:CN|HK|US|FUND|GOLD):[A-Za-z0-9.]+\b)/g;
  let out = "",
    last = 0;
  for (const m of s.matchAll(regex)) {
    out += esc(s.slice(last, m.index));
    const t = m[0];
    if (t.startsWith("**")) out += `<strong>${esc(t.slice(2, -2))}</strong>`;
    else if (t.startsWith("~~")) out += `<del>${esc(t.slice(2, -2))}</del>`;
    else if (t.startsWith("`")) out += `<code>${esc(t.slice(1, -1))}</code>`;
    else if (/^\[E\d+\]$/.test(t))
      out += `<button class="citation" data-action="show-evidence" data-id="${esc(t.slice(1, -1))}">${esc(t.slice(1, -1))}</button>`;
    else if (t.startsWith("[")) {
      const p = t.match(/^\[([^\]]+)\]\((.+)\)$/);
      const safe = /^https?:\/\//i.test(p[2]) || p[2].startsWith("#/");
      out += safe
        ? `<a href="${esc(p[2])}" ${p[2].startsWith("http") ? 'target="_blank" rel="noopener noreferrer"' : ""}>${esc(p[1])}</a>`
        : esc(p[1]);
    } else out += `<a href="${t.startsWith('FUND:') ? '#/funds/' + encodeURIComponent(t.slice(5)) : stockHref(t)}">${esc(t)}</a>`;
    last = m.index + t.length;
  }
  return out + esc(s.slice(last));
}
export function markdown(text) {
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  let out = "", listType = "", code = false, codeLanguage = "";
  const closeList = () => {
    if (listType) out += `</${listType}>`;
    listType = "";
  };
  const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
  const isTable = (i) => i + 1 < lines.length && lines[i].includes("|") && cells(lines[i + 1]).length > 1 && cells(lines[i + 1]).every((cell) => /^:?-{3,}:?$/.test(cell));
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.startsWith("```")) {
      closeList();
      if (code) out += "</code></pre>";
      else {
        codeLanguage = line.slice(3).trim().split(/\s+/)[0];
        out += `<pre><code${codeLanguage ? ` class="language-${esc(codeLanguage)}"` : ""}>`;
      }
      code = !code;
      continue;
    }
    if (code) {
      out += esc(line) + "\n";
      continue;
    }
    if (isTable(i)) {
      closeList();
      const headers = cells(line), alignments = cells(lines[i + 1]).map((cell) => cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : "");
      out += `<div class="md-table-wrap"><table class="md-table"><thead><tr>${headers.map((cell, col) => `<th${alignments[col] ? ` style="text-align:${alignments[col]}"` : ""}>${inline(cell)}</th>`).join("")}</tr></thead><tbody>`;
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        const row = cells(lines[i]);
        out += `<tr>${headers.map((_, col) => `<td${alignments[col] ? ` style="text-align:${alignments[col]}"` : ""}>${inline(row[col] || "")}</td>`).join("")}</tr>`;
        i += 1;
      }
      i -= 1;
      out += "</tbody></table></div>";
      continue;
    }
    if (/^\s*[-*+]\s/.test(line) || /^\d+[.)]\s/.test(line)) {
      const type = /^\d+[.)]\s/.test(line) ? "ol" : "ul";
      if (listType !== type) {
        closeList();
        out += `<${type}>`;
        listType = type;
      }
      out += `<li>${inline(line.replace(/^\s*(?:[-*+]|\d+[.)])\s/, ""))}</li>`;
      continue;
    }
    closeList();
    if (/^\s*(?:(?:-{3,})|(?:_{3,})|(?:\*{3,}))\s*$/.test(line)) out += '<hr class="md-rule">';
    else if (/^#{1,4}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      out += `<h${level}>${inline(line.replace(/^#+\s/, ""))}</h${level}>`;
    } else if (/^>\s?/.test(line)) out += `<blockquote><p>${inline(line.replace(/^>\s?/, ""))}</p></blockquote>`;
    else if (line.trim()) out += `<p>${inline(line)}</p>`;
  }
  closeList();
  return out + (code ? "</code></pre>" : "");
}
export function lineChart(bars) {
  const points = bars.filter(
    (b) => b.close != null && Number.isFinite(Number(b.close)),
  );
  if (points.length < 2)
    return empty(
      "还没有可绘制的历史行情",
      "点击“拉取日线”，取得真实数据后展示价格曲线。",
    );
  const values = points.map((b) => Number(b.close));
  let low = Math.min(...values),
    high = Math.max(...values);
  if (high === low) {
    high += Math.max(1, high * 0.01);
    low -= Math.max(1, low * 0.01);
  }
  const left = 62,
    right = 778,
    top = 27,
    bottom = 242;
  const coords = points.map((p, i) => [
    left + (i / (points.length - 1)) * (right - left),
    bottom - ((Number(p.close) - low) / (high - low)) * (bottom - top),
  ]);
  const path = coords
    .map((p, i) => (i ? "L" : "M") + p.map((v) => v.toFixed(2)).join(","))
    .join(" ");
  return `<svg class="chart" viewBox="0 0 810 284" role="img" aria-label="${esc(points[0].bar_time)} 至 ${esc(points.at(-1).bar_time)} 的真实日线收盘价"><defs><linearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="var(--primary)" stop-opacity=".13"/><stop offset="1" stop-color="var(--primary)" stop-opacity="0"/></linearGradient></defs>${[0, 0.25, 0.5, 0.75, 1].map((p) => `<line x1="${left}" y1="${top + p * (bottom - top)}" x2="${right}" y2="${top + p * (bottom - top)}" stroke="var(--line)" stroke-dasharray="3 5"/><text x="8" y="${top + p * (bottom - top) + 4}" class="chart-label">${number(high - p * (high - low))}</text>`).join("")}<path d="${path} L ${right},${bottom} L ${left},${bottom} Z" fill="url(#chart-area)"/><path d="${path}" fill="none" stroke="var(--primary)" stroke-width="2" vector-effect="non-scaling-stroke"/><text x="${left}" y="273" class="chart-label">${esc(points[0].bar_time)}</text><text x="${right}" y="273" class="chart-label" text-anchor="end">${esc(points.at(-1).bar_time)}</text></svg>`;
}
let toastTimer;
export function notify(text) {
  const el = document.querySelector("#toast");
  el.textContent = text;
  el.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("visible"), 3200);
}
export function showDialog(title, body, actions = "") {
  const el = document.querySelector("#app-dialog");
  document.querySelector("#dialog-content").innerHTML =
    `<div class="dialog-head"><h2 id="dialog-title">${esc(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="关闭">${icon("close")}</button></div><div class="dialog-body" id="dialog-description">${body}</div>${actions ? `<div class="dialog-actions">${actions}</div>` : ""}`;
  el.setAttribute("aria-describedby", "dialog-description");
  if (el.open) el.close();
  el.showModal();
  return el;
}
export function confirmDialog(title, body, label = "确认", danger = false) {
  return new Promise((resolve) => {
    const dialog = showDialog(
      title,
      body,
      `<button class="button" data-action="close-dialog" autofocus>返回</button><button class="button ${danger ? "danger" : "primary"}" id="dialog-confirm">${esc(label)}</button>`,
    );
    let confirmed = false;
    dialog.querySelector("#dialog-confirm").onclick = () => {
      confirmed = true;
      dialog.close();
    };
    dialog.addEventListener("close", () => resolve(confirmed), { once: true });
  });
}
