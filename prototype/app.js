import {
  renderNews,
  renderLiquidity,
  rotationMarkup,
  cleanupContext,
  handleContextSubmit,
  handleContextAction,
} from "./market-context.js";
import {
  renderIndices,
  renderFlows,
  renderFunds,
  cycleMarkup,
  cleanupIndices,
  mountMarketIndices,
  handleResearchSubmit,
  handleResearchAction,
} from "./market-research.js";
import {
  renderPaperAccounts,
  renderPaperOrders,
  handlePaperSubmit,
  handlePaperAction,
  cleanupPaper,
} from "./paper.js";
import { renderLive, handleLiveSubmit, handleLiveAction } from "./live.js";
import { renderFutuPaper, handleFutuPaperSubmit, handleFutuPaperAction } from "./futu-paper.js";
import {
  requireIdentity,
  getIdentity,
  signOut,
  renderSecurityPage,
  mountSecurityPage,
} from "./identity.js";
import { stockOverview, mountStock, updateChartRoute, dossierTab } from "./stock.js";
import { renderGold, handleGoldAction } from "./gold.js";
import {
  renderCalendarPage,
  mountCalendar,
  cleanupCalendar,
  handleCalendarAction,
  handleCalendarSubmit,
  addAICalendarPlan,
  loadCalendarState,
  startCalendarAlarms,
  stopCalendarAlarms,
} from "./calendar.js";
import { API, request, requestEvents, postOrder } from "./api.js";
import { extensionsMarkup, mountExtensions } from "./agent-extensions.js";
import { renderWikiPage, handleWikiAction } from "./investment-wiki.js";
import { renderGlossaryPage, loadGlossary, chatTermsMarkup, handleGlossaryAction } from "./ai-glossary.js";
import { renderHoldings, handleHoldingsAction, handleHoldingsSubmit, handleHoldingsScreenshot, clearHoldingsDraft } from "./holdings.js";
import { installInstrumentSearch, resolveInstrument } from "./instrument-search.js";
import {
  esc,
  icon,
  brandMark,
  markets,
  phases,
  number,
  money,
  percent,
  tone,
  time,
  stockHref,
  sectorHref,
  fresh,
  empty,
  loading,
  errorPanel,
  stat,
  resultCards,
  markdown,
  lineChart,
  notify,
  showDialog,
  confirmDialog,
  patchContent,
} from "./ui.js";
const $ = (s) => document.querySelector(s);
installInstrumentSearch();
const MARKET_PALETTE_KEY = "finch.marketPalette";
const RAIL_KEY = "finch.workspaceRail.v1";
const RAIL_MIGRATION_KEY = "finch.workspaceRail.migratedOwner";
const CHAT_SESSIONS_KEY = "finch.aiSessions.v1";
const features = [
  ["calendar", "calendar", "交易日历", "#calendar", "市场开闭市、计划与打新订阅"],
  ["watchlist", "star", "我的自选", "#watchlist", "关注标的、价格和涨跌幅"],
  ["markets", "chart", "市场总览", "#markets", "多市场行情与市场广度"],
  ["gold", "coins", "黄金行情", "#gold", "上金所现货报价、日线走势与相关新闻"],
  ["indices", "candles", "大盘与指数", "#indices", "主要指数与市场表现"],
  ["news", "file", "新闻与流动性", "#news", "财经快讯与政策事件"],
  ["liquidity", "bank", "央行流动性", "#liquidity", "逆回购公告与流动性事件"],
  ["flows", "wallet", "资金流向", "#flows", "大盘、行业与北向资金"],
  ["funds", "layers", "公募基金", "#funds", "搜索与研究各类基金"],
  ["sectors", "layers", "板块轮动与资金", "#sectors", "行业强弱、轮动与成分股"],
  ["research", "flask", "策略研究", "#research", "策略实验、回测与研究记录"],
  ["paper", "flask", "模拟炒股", "#paper", "本地与富途模拟账户、委托和持仓"],
  ["documents", "file", "研报资料", "#documents", "导入资料并交给 Agent 分析"],
  ["glossary", "layers", "AI 词条", "#glossary", "收藏词条与新闻推荐研究主题"],
  ["holdings", "wallet", "我的持仓", "#holdings", "股票、基金与黄金持仓"],
  ["security", "shield", "账户安全", "#security", "身份验证与账户安全设置"],
  ["settings", "settings", "数据与模型", "#settings", "Agent 配置、行情源和偏好"],
];
const defaultRail = ["watchlist", "calendar", "clock", "data"];
const readRailPrefs = () => {
  try {
    const value = JSON.parse(localStorage.getItem(RAIL_KEY) || "{}");
    const valid = (value.cards || []).filter((id) => [...features.map((x) => x[0]), "clock", "data"].includes(id));
    return {
      cards: [...new Set(valid)].length ? [...new Set(valid)] : defaultRail,
      wide: value.wide === true,
      visible: value.visible !== false,
      width: Math.min(Math.floor(window.innerWidth * 0.5), Math.max(270, Number(value.width) || 320)),
    };
  } catch (_error) {
    return { cards: defaultRail, wide: false, visible: true, width: 320 };
  }
};
const railPrefs = readRailPrefs();
let marketPalette = "cn";
try {
  marketPalette = localStorage.getItem(MARKET_PALETTE_KEY) === "us" ? "us" : "cn";
} catch (_error) {
  // Browsers with disabled storage still support an in-session switch.
}
document.documentElement.dataset.marketPalette = marketPalette;
function syncMarketPaletteControls() {
  const label = document.getElementById("market-palette-label");
  if (label) label.textContent = marketPalette === "us" ? "美股视图" : "A股视图";
  const toggle = document.getElementById("market-palette-toggle");
  if (toggle) toggle.setAttribute("aria-label", `当前${marketPalette === "us" ? "美股视图，绿涨红跌" : "A股视图，红涨绿跌"}；点击切换`);
  document.querySelectorAll("[data-palette]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.palette === marketPalette));
  });
  document.querySelectorAll("[data-market-legend]").forEach((legend) => {
    const rise = legend.dataset.marketLegend === "up";
    legend.textContent = marketPalette === "us"
      ? rise ? "绿涨" : "红跌"
      : rise ? "红涨" : "绿跌";
  });
}
function setMarketPalette(next) {
  if (next !== "cn" && next !== "us") return;
  marketPalette = next;
  document.documentElement.dataset.marketPalette = next;
  try { localStorage.setItem(MARKET_PALETTE_KEY, next); } catch (_error) { /* Keep the active view. */ }
  syncMarketPaletteControls();
}
syncMarketPaletteControls();
const state = {
  watch: [],
  sessions: [],
  providers: [],
  status: null,
  history: [],
  accounts: [],
  messages: [],
  chatSessions: [],
  serverChatSessions: [],
  legacyChatSessions: [],
  memoryEntries: [],
  memoryStatus: "ready",
  glossary: null,
  glossaryExpanded: false,
  sessionQuery: "",
  activeChatId: null,
  railCards: railPrefs.cards,
  railWide: railPrefs.wide,
  railVisible: railPrefs.visible,
  railWidth: railPrefs.width,
  railVersion: null,
  railCustomCards: {},
  railOverrides: {},
  expandedRailCard: null,
  railNotice: null,
  calendarDraft: null,
  draft: "",
  pastedImage: null,
  sessionImage: null,
  sending: false,
  accountId: null,
  pendingAccountQuestion: null,
  route: null,
  version: 0,
  controller: null,
  currentHash: "",
  forms: new Map(),
  patchPage: false,
};
let futuStatusTimer = null;
const titles = {
  security: "账户安全",
  chat: "AI 投研",
  watchlist: "我的自选",
  markets: "市场总览",
  gold: "黄金行情",
  indices: "大盘与指数",
  news: "新闻与流动性",
  liquidity: "央行流动性",
  flows: "资金流向",
  funds: "公募基金",
  sectors: "板块轮动与资金",
  stocks: "个股详情",
  research: "策略研究",
  documents: "研报资料",
  holdings: "我的持仓",
  paper: "模拟炒股",
  live: "实盘交易",
  settings: "数据与模型",
  memory: "投资记忆",
  glossary: "AI 词条",
  calendar: "交易日历",
};
const canonical = (id) => {
  const [m, ...rest] = id.trim().split(":");
  if (!rest.length) return id.trim();
  let s = rest.join(":");
  if (m.toUpperCase() === "HK" && /^\d+$/.test(s)) s = s.padStart(5, "0");
  return `${m.toUpperCase()}:${m.toUpperCase() === "GOLD" ? s : s.toUpperCase()}`;
};
function route() {
  const aliases = {
    accounts: "paper",
    account: "paper",
    orders: "paper",
    trading: "paper",
    quotes: "markets",
    market: "markets",
    "ai-research": "chat",
    sources: "settings",
    rotation: "sectors",
  };
  let hash = location.hash.slice(1) || "/chat";
  if (!hash.startsWith("/")) hash = "/" + (aliases[hash] || hash);
  const [path, query = ""] = hash.split("?");
  const parts = path.split("/").filter(Boolean);
  const params = new URLSearchParams(query);
  return {
    name: aliases[parts[0]] || parts[0] || "chat",
    id: parts[1] ? decodeURIComponent(parts.slice(1).join("/")) : null,
    params,
  };
}
function navItem(id, glyph, label, href = `#/${id}`) {
  const active = state.route?.name === id ||
    (id === "watchlist" && state.route?.name === "stocks") || (id === "news" && state.route?.name === "liquidity");
  return `<a class="nav-item" href="${href}" ${active ? 'aria-current="page"' : ""}>${icon(glyph)}<span>${label}</span>${id === "watchlist" ? `<span class="nav-count">${state.watch.length}</span>` : ""}</a>`;
}
function navMarkup() {
  const more = [
    ["市场研究", ["indices", "news", "liquidity", "flows", "funds", "sectors", "gold"]],
    ["研究工具", ["paper", "research", "documents", "glossary"]],
  ];
  return `<div class="nav-primary">${navItem("holdings", "wallet", "我的持仓")}${navItem("live", "wallet", "实盘交易")}${navItem("watchlist", "star", "我的自选")}${navItem("markets", "globe", "市场总览")}</div><details class="nav-more"><summary><span>${icon("grid")}更多工具</span><span class="nav-more-caret">⌄</span></summary>${more.map(([title, ids]) => `<section class="nav-subgroup"><div class="nav-label">${title}</div>${ids.map((id) => {
    const feature = features.find((x) => x[0] === id);
    const label = id === "liquidity" ? "央行流动性" : feature?.[2] || id;
    return navItem(id, feature?.[1] || "file", label);
  }).join("")}</section>`).join("")}</details>`;
}
function identityMenuMarkup() {
  const identity = getIdentity();
  const user = identity?.user || {};
  const username = user.username || identity?.username || "私人空间";
  return `<div class="account-menu-card"><div class="account-menu-avatar">${esc(username.slice(0, 1).toUpperCase())}</div><div><strong>${esc(username)}</strong><small>个人投研空间 · 本地账户</small></div></div><div class="account-menu-links"><a href="#/security">${icon("shield")}账户安全 <span>密码与验证设置</span></a><a href="#/settings?section=memory">${icon("file")}记忆保留期限 <span>会话原文与归档记忆</span></a><a href="#/settings">${icon("settings")}工作台设置 <span>Agent 与行情源</span></a></div><button class="button ghost account-signout" data-action="sign-out">退出登录</button>`;
}
const sessionDayOpen = new Map();
function shanghaiDay(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '未知日期';
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}
function sessionListMarkup() {
  const query = state.sessionQuery.trim().toLocaleLowerCase();
  const sessions = state.chatSessions.filter((session) => {
    if (!query) return true;
    const searchable = [session.title, ...(session.messages || []).map((message) => message.content || "")]
      .join(" ")
      .toLocaleLowerCase();
    return searchable.includes(query);
  });
  if (!sessions.length) return `<p class="field-help session-empty">${query ? "没有匹配的投研对话" : "新建会话后会保存在这里"}</p>`;
  const groups = new Map();
  for (const session of sessions) {
    const day = shanghaiDay(session.updated_at || session.created_at);
    if (!groups.has(day)) groups.set(day, []);
    groups.get(day).push(session);
  }
  const today = shanghaiDay();
  const yesterday = shanghaiDay(Date.now() - 86400000);
  return [...groups].map(([day, items], index) => {
    const label = day === today ? '今天' : day === yesterday ? '昨天' : day;
    const expanded = query || (sessionDayOpen.has(day) ? sessionDayOpen.get(day) : index === 0 || items.some((item) => item.id === state.activeChatId));
    return `<details class="session-day" data-day="${esc(day)}" ${expanded ? 'open' : ''}><summary><span>${esc(label)}</span><small>${items.length}</small></summary><div class="session-day-list">${items.map((session) => `<div class="session-row ${session.id === state.activeChatId ? 'is-active' : ''}"><button class="recent-button" data-action="open-session" data-id="${esc(session.id)}" title="${esc(session.title)}">${esc(session.title)}${session.source === 'browser' ? '<small>浏览器旧会话</small>' : session.source === 'research' ? '<small>历史研究</small>' : ''}</button>${session.source === 'server' ? `<button class="session-delete" data-action="delete-session" data-id="${esc(session.id)}" aria-label="删除会话 ${esc(session.title)}">${icon('close')}</button>` : ''}</div>`).join('')}</div></details>`;
  }).join('');
}
function renderSidebar() {
  const configured = state.status?.enabled;
  const username = getIdentity()?.user?.username || getIdentity()?.username || "私人空间";
  const secondaryRoute = Boolean(state.route?.name && !["chat", "calendar", "holdings", "watchlist", "markets"].includes(state.route.name));
  const desktopMoreOpen = $("#sidebar .nav-more")?.open || secondaryRoute;
  const mobileMoreOpen = $("#mobile-nav .nav-more")?.open || secondaryRoute;
  $("#sidebar").innerHTML =
    `<div class="brand-row"><a class="brand sidebar-brand" href="#/chat"><div class="brand-mark">${brandMark()}</div><div class="brand-copy"><strong>Finfreedom</strong><small>AI 投研</small></div></a></div><button class="button ghost new-chat" data-action="new-chat" ${state.sending ? "disabled" : ""}>${icon("plus")} 新建会话</button><nav class="nav-group" aria-label="工作台主导航">${navMarkup()}</nav><div class="session-heading"><span>${icon("chat")}投研对话</span><small>${state.chatSessions.length} 个</small></div><label class="session-search" aria-label="搜索投研对话">${icon("search")}<input id="session-query" type="search" value="${esc(state.sessionQuery)}" placeholder="搜索投研对话" autocomplete="off" /></label><div class="recent-list session-list" id="session-results" aria-label="投研对话">${sessionListMarkup()}</div><div class="sidebar-bottom"><button class="runtime-row account-trigger" data-action="account-menu" aria-haspopup="dialog"><span class="avatar-local">${esc(username.slice(0, 1).toUpperCase())}</span><span class="account-summary"><strong>${esc(username)}</strong><small>${identitySecurityLabel()}</small></span>${icon("settings")}</button><div class="agent-state"><span class="status-dot ${configured ? "ready" : "warn"}"></span>${configured ? "Agent 已配置" : "Agent 待配置"}</div></div>`;
  $("#mobile-nav").innerHTML = navMarkup();
  if (desktopMoreOpen) $("#sidebar .nav-more").open = true;
  if (mobileMoreOpen) $("#mobile-nav .nav-more").open = true;
}
function identitySecurityLabel() {
  const identity = getIdentity();
  return identity?.user?.mfa_enabled || identity?.mfa_enabled ? "双重验证已开启" : "个人信息与账户安全";
}
function sessionStoreKey() {
  const user = getIdentity()?.user || {};
  return `${CHAT_SESSIONS_KEY}:${user.user_id || user.id || user.username || "local"}`;
}
function privateExtensionText(value) {
  return /["']mcpServers["']\s*:|npm_config_registry\s*=/i.test(String(value || ''));
}
function loadChatSessions() {
  try {
    const sessions = JSON.parse(localStorage.getItem(sessionStoreKey()) || "[]");
    if (!Array.isArray(sessions)) return [];
    const clean = sessions.filter((item) => item?.id && Array.isArray(item.messages)).slice(0, 100).map((item) => ({
      ...item,
      title: privateExtensionText(item.title) ? '添加 MCP 连接' : item.title,
      messages: item.messages.map((message) => privateExtensionText(message.content) || privateExtensionText(message.question)
        ? { ...message, content: '添加 MCP 连接', question: null, management: true }
        : message),
    }));
    try { localStorage.setItem(sessionStoreKey(), JSON.stringify(clean)); } catch (_error) { /* In-memory sanitized copy remains usable. */ }
    return clean;
  } catch (_error) {
    return [];
  }
}
function rebuildChatSessions() {
  const server = state.serverChatSessions.map((session) => ({ ...session, source: 'server' }));
  const serverIds = new Set(server.map((session) => session.id));
  const browser = state.legacyChatSessions
    .filter((session) => !serverIds.has(session.id))
    .map((session) => ({ ...session, id: `legacy-${session.id}`, source: 'browser' }));
  const recordedRuns = new Set([
    ...server.flatMap((session) => session.run_ids || []),
    ...browser.flatMap((session) => [
      ...(session.id.startsWith('legacy-history-') ? [session.id.slice('legacy-history-'.length)] : []),
      ...(session.messages || []).map((message) => message.run_id).filter(Boolean),
    ]),
  ]);
  const research = state.history.filter((run) => run.legacy && !recordedRuns.has(run.run_id)).map((run) => ({
    id: `history-${run.run_id}`,
    source: 'research',
    title: (privateExtensionText(run.question) ? '添加 MCP 连接' : run.question || '历史投研').replace(/\s+/g, ' ').slice(0, 42),
    created_at: run.created_at,
    updated_at: run.completed_at || run.created_at,
    messages: [
      { role: 'user', content: privateExtensionText(run.question) ? '添加 MCP 连接' : run.question || '', management: privateExtensionText(run.question), created_at: run.created_at },
      { role: 'assistant', content: run.answer || run.error || '研究记录暂无回答内容', model: run.model, evidence: run.evidence || [], cards: run.cards || [], tool_calls: run.tool_calls, error: run.error, created_at: run.completed_at || run.created_at },
    ],
  }));
  state.chatSessions = [...server, ...browser, ...research]
    .sort((a, b) => Date.parse(b.updated_at || b.created_at) - Date.parse(a.updated_at || a.created_at));
}
function persistChatSession() {
  if (!state.activeChatId || !state.messages.length || /^(?:legacy-|history-)/.test(state.activeChatId)) return;
  const firstQuestion = state.messages.find((message) => message.role === "user")?.content || "新的 AI 投研会话";
  const now = new Date().toISOString();
  const existing = state.chatSessions.find((item) => item.id === state.activeChatId);
  const session = {
    id: state.activeChatId,
    source: 'server',
    title: existing?.title && existing.title !== '图片待提问' ? existing.title : firstQuestion.replace(/\s+/g, " ").slice(0, 42),
    updated_at: now,
    messages: state.messages.filter((message) => !message.pending).slice(-40).map(({ imagePreview, ...message }) => message),
  };
  state.serverChatSessions = [session, ...state.serverChatSessions.filter((item) => item.id !== session.id)].slice(0, 100);
  rebuildChatSessions();
  renderSidebar();
  const title = $("#active-session-title");
  if (title) title.textContent = session.title;
}
let railSaveQueue = Promise.resolve();
function saveRailPrefs() {
  try { localStorage.setItem(RAIL_KEY, JSON.stringify({ cards: state.railCards, wide: state.railWide, visible: state.railVisible, width: state.railWidth })); } catch (_error) { /* Use current layout for this visit. */ }
  const identity = getIdentity();
  if (!identity || state.railVersion === null) return;
  const data = { cards: [...state.railCards], wide: state.railWide, visible: state.railVisible,
    expanded_card: state.expandedRailCard,
    width: state.railWidth, custom_cards: structuredClone(state.railCustomCards), overrides: structuredClone(state.railOverrides) };
  railSaveQueue = railSaveQueue.then(async () => {
    if (getIdentity() !== identity) return;
    try {
      const saved = await request('/workspace/cards', { method: 'PUT',
        body: { data, expected_version: state.railVersion } });
      if (getIdentity() === identity) state.railVersion = saved.version;
    } catch (error) {
      if (error.status === 409 && getIdentity() === identity) {
        const current = await request('/workspace/cards');
        applyRailState(current);
        renderUtilityRail();
        notify('卡片已在其他会话更新，已显示最新版本', 'error');
      } else notify(`卡片设置保存失败：${error.message}`, 'error');
    }
  });
}
function applyRailState(data) {
  state.railCards = data.cards || defaultRail;
  state.railWide = data.wide === true;
  state.railVisible = data.visible !== false;
  state.railWidth = data.width || 320;
  state.railCustomCards = data.custom_cards || {};
  state.railOverrides = data.overrides || {};
  state.expandedRailCard = data.expanded_card || null;
  state.railVersion = data.version;
}
function focusRailCard(id, expanded = true) {
  const featureId = id === "market_clock" ? "clock" : id;
  if (!state.railCards.includes(featureId)) state.railCards = [featureId, ...state.railCards];
  state.expandedRailCard = expanded ? featureId : null;
  state.railNotice = featureId;
  saveRailPrefs();
  renderUtilityRail();
  setTimeout(() => {
    if (state.railNotice === featureId) {
      state.railNotice = null;
      renderUtilityRail();
    }
  }, 5000);
}
function utilityCardBody(id) {
  if (state.railCustomCards[id]) return `<div class="utility-note-body">${markdown(state.railCustomCards[id].body)}</div>`;
  const feature = features.find((item) => item[0] === id);
  if (id === "watchlist") return state.watch.length
    ? `<div class="utility-watch-list">${state.watch.slice(0, 5).map((quote) => `<div class="utility-watch-row"><a href="${stockHref(quote.instrument_id)}"><strong>${esc(quote.name || quote.instrument_id)}</strong><small>${esc(quote.instrument_id)} · ${money(quote.last, quote.currency)}</small></a><span class="mono ${tone(quote.change_percent)}">${percent(quote.change_percent)}</span><button class="utility-watch-remove" data-action="toggle-watch" data-id="${esc(quote.instrument_id)}" aria-label="移除 ${esc(quote.name || quote.instrument_id)}">×</button></div>`).join("")}</div><a class="utility-card-foot" href="#/watchlist">管理 ${state.watch.length} 个自选 →</a>`
    : `<div class="utility-empty">${icon("star")}<span>关注标的会显示在这里</span><a href="#/markets">添加自选 →</a></div>`;
  if (id === "clock" || id === "calendar") {
    const sessions = state.sessions.filter((item) => ["CN", "HK", "US"].includes(item.market));
    return `<div class="utility-clock-list">${sessions.map((item) => `<div class="utility-clock-row"><span><strong>${esc(markets[item.market] || item.market)}</strong><small>${esc(item.timezone || "")}</small></span><span class="utility-phase">${phases[item.phase] || esc(item.phase)}<small>${item.next_open ? "下次 " + time(item.next_open) : "交易所时区"}</small></span></div>`).join("") || '<p class="field-help">正在读取市场时钟…</p>'}</div>${id === "calendar" ? `<a class="utility-card-foot" href="#/calendar">打开交易日历 →</a>` : `<a class="utility-card-foot" href="#/markets">查看市场 →</a>`}`;
  }
  if (id === "markets" || id === "data") {
    const available = state.providers.filter((item) => item.quote_count > 0).length;
    const gaps = state.providers.filter((item) => ["error", "partial", "stale"].includes(item.state)).length;
    return `<div class="utility-stat-row"><strong>${available}</strong><span>个市场有缓存</span><strong class="${gaps ? "market-down" : "market-up"}">${gaps}</strong><span>个数据缺口</span></div><div class="utility-provider-list">${state.providers.slice(0, 4).map((item) => `<div><span>${esc(item.market_name)}</span><small>${number(item.quote_count, 0)} 条 · ${esc(item.state === "connected" ? "可用" : item.state === "partial" ? "部分可用" : item.state === "stale" ? "缓存过期" : item.state === "error" ? "连接异常" : "等待")}</small></div>`).join("")}</div><a class="utility-card-foot" href="#/${id === "data" ? "settings" : "markets"}">${id === "data" ? "查看连接与数据源 →" : "打开市场总览 →"}</a>`;
  }
  if (id === "security") return `<div class="utility-user-preview"><span class="avatar-local">${esc((getIdentity()?.user?.username || "我").slice(0, 1))}</span><span><strong>${esc(getIdentity()?.user?.username || getIdentity()?.username || "私人空间")}</strong><small>${identitySecurityLabel()}</small></span></div><a class="utility-card-foot" href="#/security">查看账户安全 →</a>`;
  const countInfo = {
    indices: `${state.providers.filter((item) => item.quote_count > 0).length} 个市场数据源可用`,
    news: "财经快讯、政策与事件观察",
    liquidity: "公开市场操作与流动性公告",
    flows: "基金信息与市场资金统计",
    sectors: "行业轮动、涨跌和资金观察",
    research: `${state.history.length} 条近期投研记录`,
    documents: "管理研报、财报与公告资料",
  }[id] || feature?.[4] || "查看工作台功能";
  return `<div class="utility-feature-preview"><span class="utility-feature-icon">${icon(feature?.[1] || "grid")}</span><p>${esc(countInfo)}</p></div><a class="utility-card-foot" href="${feature?.[3] || "#/chat"}">打开${esc(feature?.[2] || "功能页面")} →</a>`;
}
function utilityRailMarkup() {
  const visibleCards = state.expandedRailCard ? state.railCards.filter((id) => id === state.expandedRailCard) : state.railCards;
  const noticeLabel = features.find((item) => item[0] === state.railNotice)?.[2] || "我的自选";
  const noticeMarkup = state.railNotice
    ? `<div class="rail-notice">${icon("spark")}已更新「${esc(noticeLabel)}」卡片</div>`
    : "";
  return `<div class="utility-rail-head"><div><span class="eyebrow">AI WORKSPACE</span><h2>工作台卡片</h2><p>拖动排序 · 卡片内容可展开</p></div><div class="utility-rail-head-actions"><button class="icon-button" data-action="manage-rail" aria-label="管理工作台卡片" title="管理卡片">${icon("settings")}</button><button class="icon-button" data-action="hide-rail" aria-label="隐藏工作台卡片栏" title="隐藏卡片栏">${icon("close")}</button></div></div><div class="utility-rail-tools"><button class="button small ghost" data-action="manage-rail">${icon("plus")} 添加 / 管理</button><button class="icon-button" data-action="toggle-rail-width" aria-label="${state.railWide ? "收窄卡片栏" : "加宽至半屏"}" title="${state.railWide ? "收窄" : "加宽至半屏"}">${icon("arrow")}</button></div>${noticeMarkup}<div class="utility-card-list ${state.expandedRailCard ? "has-expanded" : ""}" id="utility-card-list">${visibleCards.map((id) => {
    const feature = features.find((item) => item[0] === id);
    const cardTitle = state.railCustomCards[id]?.title || state.railOverrides[id]?.title || (id === "clock" ? "市场时钟" : id === "data" ? "数据连接" : feature?.[2] || id);
    const cardRoute = id === "clock" ? "#/markets" : id === "data" ? "#/settings" : feature?.[3] || "#/chat";
    const expanded = state.expandedRailCard === id;
    return `<article class="utility-card ${expanded ? "is-expanded" : ""} ${state.railNotice === id ? "is-notice" : ""}" draggable="true" data-rail-card="${esc(id)}"><header class="utility-card-head"><button class="utility-drag" aria-label="拖动或排序 ${esc(cardTitle)}" title="拖动排序">⠿</button><a href="${cardRoute}" class="utility-card-title">${icon(feature?.[1] || (id === "clock" ? "clock" : "grid"))}<strong>${esc(cardTitle)}</strong></a><button class="icon-button" data-action="move-rail-card" data-id="${esc(id)}" data-direction="up" aria-label="${esc(cardTitle)}上移">↑</button><button class="icon-button" data-action="move-rail-card" data-id="${esc(id)}" data-direction="down" aria-label="${esc(cardTitle)}下移">↓</button><button class="icon-button" data-action="expand-rail-card" data-id="${esc(id)}" aria-label="${expanded ? "收起" : "展开"}${esc(cardTitle)}">${expanded ? "↙" : "⛶"}</button></header><div class="utility-card-body">${utilityCardBody(id)}${state.railOverrides[id]?.note ? `<p class="utility-card-note">${esc(state.railOverrides[id].note)}</p>` : ''}</div><footer class="utility-card-actions">${state.railCustomCards[id] ? '' : `<a href="${cardRoute}">全页打开 ↗</a>`}<button data-action="hide-rail-card" data-id="${esc(id)}">隐藏</button></footer></article>`;
  }).join("") || '<div class="utility-empty utility-empty-rail"><p>右栏还没有卡片</p><button class="button small" data-action="manage-rail">添加一个功能卡片</button></div>'}</div>`;
}
function renderUtilityRail() {
  const rail = $("#utility-rail");
  const workspace = $(".workspace");
  if (!rail || !workspace) return;
  const inChat = route().name === "chat";
  const showRail = inChat && state.railVisible;
  workspace.classList.toggle("rail-hidden", !showRail);
  workspace.classList.toggle("rail-wide", showRail && state.railWide);
  rail.hidden = !showRail;
  const toggle = $(".utility-toggle");
  toggle.hidden = !inChat;
  toggle.setAttribute("aria-label", showRail ? "打开工作台卡片窗口" : "显示工作台卡片栏");
  toggle.setAttribute("aria-expanded", String(showRail));
  workspace.style.setProperty("--utility-width", state.railWide ? "50vw" : `${state.railWidth}px`);
  rail.innerHTML = `<button class="utility-resizer" data-action="resize-rail" aria-label="拖动调整右栏宽度" title="拖动调整宽度"></button>${utilityRailMarkup()}`;
  const dialogContent = $("#utility-dialog-content");
  if (dialogContent && $("#utility-dialog").open) dialogContent.innerHTML = utilityRailMarkup();
}
function manageRail() {
  const options = [...features.map((feature) => ({ id: feature[0], title: feature[2], glyph: feature[1], description: feature[4] })), { id: "clock", title: "市场时钟", glyph: "clock", description: "A 股、港股和美股交易状态" }, { id: "data", title: "数据连接", glyph: "settings", description: "数据源缓存与可用情况" }, ...Object.entries(state.railCustomCards).map(([id, card]) => ({ id, title: card.title, glyph: 'file', description: '自定义笔记卡片' }))];
  showDialog("管理工作台卡片", `<p>勾选显示在右侧栏的卡片；拖动右侧卡片或用方向按钮调整顺序。点击卡片标题可打开完整功能页。</p><div class="rail-manager-list">${options.map((item) => `<label class="rail-manager-option"><input type="checkbox" data-rail-select="${esc(item.id)}" ${state.railCards.includes(item.id) ? "checked" : ""}><span>${icon(item.glyph)}</span><span><strong>${esc(item.title)}</strong><small>${esc(item.description)}</small></span></label>`).join("")}</div>`, `<button class="button" data-action="close-dialog">取消</button><button class="button primary" data-action="save-rail">保存卡片</button>`);
}
async function refreshShell() {
  if (!getIdentity() || getIdentity().setup_required) return [];
  const requestedIdentity = getIdentity();
  const jobs = [
    ["railState", "/workspace/cards"],
    ["watch", "/watchlist"],
    ["sessions", "/markets/status"],
    ["providers", "/providers"],
    ["status", "/ai/status"],
    ["history", "/ai/research?limit=100"],
    ["serverChatSessions", "/ai/sessions?limit=100"],
    ["accounts", "/accounts"],
  ];
  const results = await Promise.allSettled(
    jobs.map(async ([key, path]) => {
      const data = await request(path, { timeout: 12000 });
      if (getIdentity() === requestedIdentity) {
        if (key === "railState") {
          let current = data;
          const owner = requestedIdentity.user?.user_id || requestedIdentity.user?.id || requestedIdentity.user?.username;
          if (data.version === 0 && localStorage.getItem(RAIL_KEY) && !localStorage.getItem(RAIL_MIGRATION_KEY)) {
            try {
              const legacy = readRailPrefs();
              current = await request('/workspace/cards', { method: 'PUT', body: {
                data: { ...legacy, custom_cards: {}, overrides: {}, expanded_card: null }, expected_version: 0 } });
              if (owner) localStorage.setItem(RAIL_MIGRATION_KEY, owner);
            } catch (error) {
              if (error.status === 409) current = await request('/workspace/cards');
              else throw error;
            }
          }
          if (getIdentity() === requestedIdentity) applyRailState(current);
        }
        else state[key] = key === "sessions" ? data.markets : data;
      }
    }),
  );
  if (getIdentity() !== requestedIdentity) return results;
  await loadCalendarState(true);
  rebuildChatSessions();
  renderSidebar();
  renderUtilityRail();
  const utilityDialog = $("#utility-dialog-content");
  if (utilityDialog && $("#utility-dialog").open) utilityDialog.innerHTML = utilityRailMarkup();
  const note = $("#model-note");
  if (note) note.innerHTML = modelNote();
  if (!state.status?.supports_vision) state.pastedImage = null;
  const imagePreview = $("#chat-image-preview");
  if (imagePreview) imagePreview.innerHTML = pastedImageMarkup();
  const visionHint = $("#chat-vision-hint");
  if (visionHint) visionHint.textContent = state.accountId ? "本次允许读取指定账户" : state.status?.supports_vision ? "粘贴图片 · Enter 发送" : "Enter 发送 · Shift + Enter 换行";
  if (state.route?.name === "calendar") renderRoute();
  return results;
}
function modelNote() {
  if (state.memoryStatus === "degraded")
    return `<span><span class="status-dot warn"></span>投资记忆暂时不可用；本轮只依据当前数据分析</span>`;
  if (state.status?.enabled)
    return `<span><span class="status-dot ready"></span> ${esc(state.status.primary_model)}</span><span>平台 MCP 工具已就绪</span>`;
  return `<span>配置模型后，Finfreedom 可以调取数据并整理研究结论。</span><a class="text-link" href="#/settings">配置模型 ↗</a>`;
}
function pastedImageMarkup() {
  if (!state.pastedImage) return "";
  if (!state.status?.supports_vision) return "";
  const image = state.pastedImage;
  const ready = !!image.uploaded?.content;
  const failed = !!image.error || !!image.uploaded?.analysis_error;
  const status = ready ? `${icon('check')}已识别，图片信息已加入当前会话` : failed ? `${icon('close')}识别失败，发送时重试` : '<span class="spinner" aria-hidden="true"></span>正在识别图片…';
  return `<div class="chat-image-chip"><img src="${esc(image.dataUrl)}" alt="待识别的剪贴板图片" /><div class="chat-image-info"><span>${esc(image.filename)} · ${Math.ceil(image.size / 1024)} KB${image.uploaded?.sha256 ? ` · SHA-256 ${esc(image.uploaded.sha256.slice(0, 12))}…` : ''}</span><span class="chat-image-status ${ready ? 'is-ready' : failed ? 'is-error' : 'is-loading'}">${status}</span></div><button type="button" data-action="remove-chat-image" aria-label="移除粘贴的图片">${icon("close")}</button></div>`;
}
function rejectPastedImage() {
  state.pastedImage = null;
  const preview = $("#chat-image-preview");
  if (preview) preview.innerHTML = "";
  state.messages.push({ role: "assistant", content: "当前模型不支持图片识别。请在模型配置中选择支持视觉的模型后重试。", management: true, created_at: new Date().toISOString() });
  updateMessages();
}
function handleChatImagePaste(event) {
  const item = [...(event.clipboardData?.items || [])].find((entry) => entry.kind === "file" && entry.type.startsWith("image/"));
  if (!item) return;
  event.preventDefault();
  if (!state.status?.supports_vision) return rejectPastedImage();
  const file = item.getAsFile();
  if (!file || !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type) || file.size > 5 * 1024 * 1024) {
    notify("请复制不超过 5 MB 的 PNG、JPEG、GIF 或 WebP 图片");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    if (typeof reader.result !== "string" || !reader.result.startsWith("data:image/")) return;
    const pasted = { dataUrl: reader.result, filename: file.name || `clipboard-${Date.now()}.png`, size: file.size };
    state.pastedImage = pasted;
    const preview = $("#chat-image-preview");
    if (preview) preview.innerHTML = pastedImageMarkup();
    const session_id = state.activeChatId && !/^(?:history-|legacy-)/.test(state.activeChatId) ? state.activeChatId : null;
    pasted.uploadPromise = request('/ai/images', {
      method: 'POST', body: { image_data_url: pasted.dataUrl, filename: pasted.filename, session_id }, timeout: 65000,
    }).then((uploaded) => {
      pasted.uploaded = uploaded;
      if (state.pastedImage === pasted) {
        state.activeChatId = uploaded.session_id;
        state.sessionImage = uploaded;
        if (!state.serverChatSessions.some((session) => session.id === uploaded.session_id)) {
          state.serverChatSessions.unshift({ id: uploaded.session_id, source: 'server', title: '图片待提问', created_at: uploaded.created_at, updated_at: uploaded.created_at, messages: [] });
          rebuildChatSessions();
          renderSidebar();
        }
        const target = $('#chat-image-preview');
        if (target) target.innerHTML = pastedImageMarkup();
      }
      return uploaded;
    }).catch((error) => {
      pasted.error = error.message;
      if (state.pastedImage === pasted) {
        const target = $('#chat-image-preview');
        if (target) target.innerHTML = pastedImageMarkup();
        notify(`图片预解析失败：${error.message}。发送时会重试。`);
      }
      return null;
    });
  };
  reader.onerror = () => notify("读取剪贴板图片失败，请重新复制后粘贴");
  reader.readAsDataURL(file);
}
function heading(title, description, actions = "", eyebrow = "") {
  return `<div class="page-heading"><div>${eyebrow ? `<div class="eyebrow">${esc(eyebrow)}</div>` : ""}<h1 id="page-title">${esc(title)}</h1>${description ? `<p>${esc(description)}</p>` : ""}</div>${actions ? `<div class="actions">${actions}</div>` : ""}</div>`;
}
function panel(title, content, subtitle = "") {
  return `<section class="panel"><div class="panel-header"><div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div></div>${content}</section>`;
}
function page(content) {
  return `<div class="content-page">${content}</div>`;
}
function setPage(html) {
  const localUpdate = state.patchPage;
  if (localUpdate) patchContent($("#page"), html);
  else $("#page").innerHTML = html;
  state.patchPage = false;
  if (!localUpdate) restoreForm();
}
function draftKey(form) {
  return (
    form.id +
    ":" +
    (state.route?.params.get("instrument") || "") +
    ":" +
    (state.route?.params.get("account") || "")
  );
}
function rememberForm() {
  for (const form of document.querySelectorAll("#page form[data-draft]")) {
    const data = {};
    for (const [key, value] of new FormData(form)) {
      if (typeof value === "string" && key !== "authorize") data[key] = value;
    }
    state.forms.set(draftKey(form), data);
  }
}

function restoreForm() {
  for (const form of document.querySelectorAll("#page form[data-draft]")) {
    const saved = state.forms.get(draftKey(form));
    if (saved)
      for (const [key, value] of Object.entries(saved)) {
        const input = form.elements.namedItem(key);
        if (input && input.type !== "file") input.value = value;
      }
  }
}
function welcome() {
  return `<div class="chat-welcome"><div class="welcome-symbol">${brandMark()}</div><h1>今天，想研究什么？<span>从一个问题，到一份有据可查的判断。</span></h1><p>和 Finfreedom 一起看个股、拆解板块，或读一份财报。需要深入时，直接从回答进入对应的数据页面。</p>${chatTermsMarkup(state)}<div class="prompt-grid"><button class="prompt-card" data-action="prompt" data-question="请把我提供的持仓信息导入我的持仓，先生成草稿供我核对。">${icon("file")}<strong>导入持仓</strong><small>粘贴文字或截图；保存前可核对</small></button><button class="prompt-card" data-action="prompt" data-question="请结合最新新闻、央行流动性和大盘指数，分析行业今日/5日/10日轮动，找出相对改善和转弱板块，说明数据缺口。">${icon("chart")}<strong>研究板块轮动</strong><small>新闻、流动性与行业相对强弱</small></button></div><div class="chat-intro-line">${icon("link")}每条数据卡片都能继续打开，查看详细指标与来源。</div></div>`;
}
function userImageMarkup(message) {
  const source = message.imageId
    ? `/api/v1/ai/images/${encodeURIComponent(message.imageId)}/content`
    : message.imagePreview;
  if (!source) return message.imageAttached ? '<span class="chat-image-label">已粘贴图片</span>' : '';
  return `<figure class="chat-image-figure"><img class="chat-message-image" src="${esc(source)}" alt="${esc(message.imageName || '对话图片')}" /><figcaption>${esc(message.imageName || '已解析图片')}${message.imageSize ? ` · ${Math.ceil(message.imageSize / 1024)} KB` : ''}${message.imageHash ? ` · SHA-256 ${esc(message.imageHash.slice(0, 12))}…` : ''}</figcaption></figure>`;
}
const researchToolLabels = {
  get_account_snapshot: '真实持仓', get_watchlist: '自选清单', get_market_news: '财经快讯',
  get_macro_liquidity: '央行流动性', get_sector_rotation: '行业轮动',
  get_market_overview: '市场概览', get_index_analysis: '指数趋势',
  get_instrument_research: '标的行情', get_stock_dossier: '公司资料',
  get_investment_memory: '投资记忆', get_memory_entry: '记忆条目',
  get_sector_overview: '行业数据', get_market_flow_history: '资金分类',
  get_fund_holdings: '基金披露持仓', get_stock_financials: '财务数据',
};
function researchToolsMarkup(message) {
  const tools = message.progressTools || [];
  const working = tools.some((tool) => tool.state === 'running');
  return tools.length ? `<details class="research-tools" ${message.toolsExpanded ? 'open' : ''}><summary>研究过程 · ${tools.length} 次数据调用${working ? ' · 查询中' : ''}</summary><ol>${tools.map((tool) => `<li><span class="research-tool-state ${tool.state}"></span><span>${esc(researchToolLabels[tool.name] || tool.name)}</span><small>${tool.state === 'running' ? '查询中' : tool.state === 'error' ? '未取得数据' : '已返回'}</small></li>`).join('')}</ol></details>` : '';
}
function researchProgressMarkup(message) {
  return `<div class="research-progress"><div class="pending-line" role="status"><span class="spinner" aria-hidden="true"></span>${esc(message.progressStatus || '正在准备研究…')}</div>${researchToolsMarkup(message)}${message.streamText ? `<div class="stream-answer" aria-label="正在生成回答">${esc(message.streamText)}</div>` : ''}</div>`;
}
function messageMarkup(m, i) {
  const isUser = m.role === "user";
  const cards = m.cards?.length ? `<section class="answer-components" aria-label="行情与工具数据"><div class="answer-components-title">行情与工具数据 <span>来自本次回答调用的数据</span></div><div class="result-cards">${resultCards(m.cards)}</div></section>` : '';
  const error = `<div class="alert error" role="alert">${esc(m.error)}<br>${m.question ? `<button class="button small ghost" data-action="retry-chat" data-index="${i}">重新发送</button>` : ''} <a class="text-link" href="#/settings">查看模型与数据状态</a></div>`;
  const body = m.pending ? researchProgressMarkup(m) : m.error ? error : isUser ? `${userImageMarkup(m)}${esc(m.content)}` : `${researchToolsMarkup(m)}${cards}${markdown(m.content)}`;
  const footer = !isUser && !m.pending && !m.error ? `<footer class="message-actions"><button data-action="copy-message" data-index="${i}">${icon("copy")}复制</button><button data-action="all-evidence" data-index="${i}">${icon("link")}${m.evidence?.length || 0} 条数据证据</button>${m.calendarDraft ? `<button class="calendar-ai-save" data-action="calendar-add-ai" data-index="${i}" data-date="${esc(m.calendarDraft.date)}" data-category="${esc(m.calendarDraft.category)}">加入 ${esc(m.calendarDraft.date)} 日历</button>` : ""}<span>${m.tool_calls || 0} 次工具调用</span></footer>` : '';
  return `<article class="message ${isUser ? "user" : "assistant"}" data-message="${i}"><header class="message-meta"><span class="message-avatar ${isUser ? "" : "agent"}">${isUser ? "我" : icon("spark")}</span><strong>${isUser ? "你" : "Finfreedom"}</strong>${m.model ? `<span class="muted">${esc(m.model)}</span>` : ""}<time>${time(m.created_at)}</time></header><div class="message-content">${body}</div>${footer}</article>`;
}
function updateStreamingBubble(message) {
  const scroll = $('#messages');
  const article = document.querySelector(`[data-message="${state.messages.indexOf(message)}"]`);
  if (!scroll || !article) return;
  const nearBottom = scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 100;
  const disclosure = article.querySelector('.research-tools');
  if (disclosure) message.toolsExpanded = disclosure.open;
  article.querySelector('.message-content').innerHTML = researchProgressMarkup(message);
  if (nearBottom) scroll.scrollTop = scroll.scrollHeight;
}
function updateMessages(follow = true) {
  const el = $("#messages-inner");
  if (!el) return;
  const scroll = $("#messages");
  const should =
    follow ||
    scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 100;
  el.innerHTML = state.messages.length
    ? state.messages.map(messageMarkup).join("")
    : welcome();
  if (should) scroll.scrollTop = scroll.scrollHeight;
  renderSidebar();
}
function renderChat() {
  setPage(
    `<div class="chat-layout"><section class="conversation" aria-label="AI 投研对话"><header class="chat-heading"><span><span class="agent-spark">${icon("spark")}</span><strong id="page-title">AI 投研</strong> <span class="muted">/ <span id="active-session-title">${esc(state.chatSessions.find((item) => item.id === state.activeChatId)?.title || "当前会话")}</span></span></span><a class="button small ghost chat-memory-link" href="#/memory">${icon("file")} 投资记忆</a><button class="button small" data-action="daily-advice">持仓操作建议</button><button class="icon-button" data-action="new-chat" aria-label="新建 AI 投研会话" ${state.sending ? "disabled" : ""}>${icon("plus")}</button></header><div class="messages" id="messages" aria-label="对话记录"><div class="messages-inner" id="messages-inner"></div></div><div class="composer-wrap"><div class="model-note" id="model-note">${modelNote()}</div><form id="chat-form" class="composer" novalidate><label class="sr-only" for="chat-input">向 Finfreedom 提问</label><div id="chat-image-preview" class="chat-image-preview" aria-live="polite">${pastedImageMarkup()}</div><textarea id="chat-input" class="resize-none" name="question" rows="2" placeholder="问一只股票、一个板块，或交给 Finfreedom 一份材料…" maxlength="4000">${esc(state.draft)}</textarea><div class="composer-footer"><a class="icon-button" href="#/documents" aria-label="上传研报或财报">${icon("paperclip")}</a><a class="icon-button" href="#/settings?section=skills" aria-label="管理 Skills" title="管理 Skills">${icon("plus")}</a><button class="icon-button ${state.accountId ? "positive" : ""}" type="button" data-action="account-context" aria-label="选择本次对话的账户上下文">${icon("wallet")}</button><span class="hint" id="chat-vision-hint">${state.accountId ? "本次允许读取指定账户" : state.status?.supports_vision ? "粘贴图片 · Enter 发送" : "Enter 发送 · Shift + Enter 换行"}</span><button class="send-button" id="send-button" aria-label="发送研究问题" ${state.sending ? "disabled" : ""}>${state.sending ? '<span class="spinner"></span>' : icon("up")}</button></div></form></div></section></div>`,
  );
  updateMessages(false);
  loadGlossary().then((glossary) => {
    state.glossary = glossary;
    if (state.route?.name === 'chat' && !state.messages.length) updateMessages(false);
  }).catch(() => {
    state.glossary = { terms: [], recommendations: [] };
    if (state.route?.name === 'chat' && !state.messages.length) updateMessages(false);
  });
  $("#chat-input").addEventListener("input", (e) => {
    state.draft = e.target.value;
    e.target.style.height = "auto";
    e.target.style.height = Math.min(150, e.target.scrollHeight) + "px";
  });
  $("#chat-input").addEventListener("paste", handleChatImagePaste);
  $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendChat();
    }
  });
  const messages = $("#messages");
  messages.scrollTop = state.messages.length ? messages.scrollHeight : 0;
}
async function sendChat(question = state.draft, reuseImageId = null) {
  question = question.trim();
  const pastedImage = state.pastedImage;
  if (!question && pastedImage) question = "请识别并描述这张图片。";
  if (!question || state.sending) return;
  if (pastedImage && !state.status?.supports_vision) {
    rejectPastedImage();
    return;
  }
  const privateMaterial = privateExtensionText(question);
  const displayQuestion = privateMaterial ? '私密配置已提交给 Agent（内容已隐藏）' : question;
  const history = state.messages
    .filter((m) => !m.error && !m.pending && !m.management)
    .slice(-10)
    .map((m) => ({ role: m.role, content: m.content }));
  const userMessage = {
    role: "user",
    content: displayQuestion,
    imageAttached: !!pastedImage || !!reuseImageId,
    imageId: reuseImageId,
    imagePreview: pastedImage?.dataUrl || null,
    message_id: crypto.randomUUID(),
    management: privateMaterial,
    created_at: new Date().toISOString(),
  };
  state.messages.push(userMessage);
  const pending = {
    role: "assistant",
    pending: true,
    progressStatus: '正在处理请求…',
    progressTools: [],
    streamText: '',
    created_at: new Date().toISOString(),
    question: privateMaterial ? null : question,
    management: privateMaterial,
    calendarDraft: privateMaterial ? null : state.calendarDraft,
  };
  state.calendarDraft = null;
  state.messages.push(pending);
  let paintTimer = null;
  state.sending = true;
  state.draft = "";
  state.pastedImage = null;
  const imagePreview = $("#chat-image-preview");
  if (imagePreview) imagePreview.innerHTML = "";
  const input = $("#chat-input");
  if (input) {
    input.value = "";
    input.style.height = "auto";
    input.focus();
  }
  updateMessages();
  const btn = $("#send-button");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
  }
  try {
    const uploaded = pastedImage ? await pastedImage.uploadPromise : reuseImageId ? { image_id: reuseImageId, session_id: state.activeChatId } : null;
    if (uploaded) {
      state.activeChatId = uploaded.session_id;
      state.sessionImage = uploaded;
      userMessage.imageId = uploaded.image_id;
      userMessage.imageName = uploaded.filename || pastedImage?.filename;
      userMessage.imageSize = uploaded.byte_size || pastedImage?.size;
      userMessage.imageHash = uploaded.sha256;
    }
    if (!state.activeChatId || /^(?:history-|legacy-)/.test(state.activeChatId)) {
      const created = await request("/ai/sessions", { method: "POST", body: { title: displayQuestion.slice(0, 120) } });
      state.activeChatId = created.id;
      state.serverChatSessions = [created, ...state.serverChatSessions];
      rebuildChatSessions();
      renderSidebar();
    }
    const body = {
      question,
      history,
      max_tool_calls: 16,
    };
    body.session_id = state.activeChatId;
    body.client_message_id = userMessage.message_id;
    if (state.accountId) body.account_id = state.accountId;
    if (uploaded) body.image_id = uploaded.image_id;
    else if (pastedImage) body.image_data_url = pastedImage.dataUrl;
    let result = null;
    const paint = () => {
      if (paintTimer !== null) return;
      paintTimer = setTimeout(() => {
        paintTimer = null;
        updateStreamingBubble(pending);
      }, 70);
    };
    await requestEvents('/ai/chat/stream', { body, timeout: 190000, onEvent: (event) => {
      if (event.type === 'error') throw new Error(event.message || 'Agent 运行失败');
      if (event.type === 'done') { result = event.result; return; }
      if (event.type === 'run') pending.run_id = event.run_id;
      if (event.type === 'status') pending.progressStatus = event.message;
      if (event.type === 'tool_start') {
        pending.progressTools.push({ name: event.name, state: 'running' });
        pending.progressStatus = '正在核对数据来源';
      }
      if (event.type === 'tool_end') {
        const item = [...pending.progressTools].reverse().find((tool) => tool.name === event.name && tool.state === 'running');
        if (item) item.state = event.ok ? 'done' : 'error';
      }
      if (event.type === 'answer_reset') pending.streamText = '';
      if (event.type === 'answer_delta') {
        pending.streamText += event.text || '';
        pending.progressStatus = '正在撰写回答';
      }
      paint();
    } });
    if (!result) throw new Error('连接提前结束，Agent 结果尚未返回。');
    if (paintTimer !== null) { clearTimeout(paintTimer); paintTimer = null; }
    if (result.display_question) userMessage.content = result.display_question;
    if (result.session_id) state.activeChatId = result.session_id;
    state.memoryStatus = result.memory_status || "ready";
    Object.assign(pending, {
      pending: false,
      content: result.answer,
      model: result.model,
      evidence: result.evidence,
      cards: result.cards || [],
      tool_calls: result.tool_calls,
      run_id: result.run_id,
    });
    delete pending.streamText;
    delete pending.progressStatus;
    refreshShell();
  } catch (error) {
    Object.assign(pending, { pending: false, error: error.message, question: privateMaterial ? null : question });
    delete pending.streamText;
    delete pending.progressStatus;
  } finally {
    if (paintTimer !== null) clearTimeout(paintTimer);
    state.sending = false;
    persistChatSession();
    updateMessages(false);
    const send = $("#send-button");
    if (send) {
      send.disabled = false;
      send.innerHTML = icon("up");
    }
  }
}
function ask(question) {
  state.draft = question;
  if (state.route?.name === "chat") {
    const input = $("#chat-input");
    input.value = question;
    input.focus();
  } else {
    location.hash = "/chat";
    setTimeout(() => $("#chat-input")?.focus(), 30);
  }
}
function quoteTable(rows, { watchButtons = true, metrics = false } = {}) {
  if (!rows.length) return empty("没有找到证券", "换个关键词或市场再试。");
  return `<div class="table-scroll"><table class="data-table"><thead><tr><th>标的</th><th>价格 / 净值</th><th>涨跌幅</th>${metrics ? "<th>20 日均线</th><th>20 日年化波动</th>" : ""}<th>行情状态</th><th>数据时点</th>${watchButtons ? "<th>自选</th>" : ""}</tr></thead><tbody>${rows.map((q) => `<tr><td><a class="stock-link" href="${stockHref(q.instrument_id)}">${esc(q.name || q.instrument_id)}</a><small class="mono">${esc(q.instrument_id)}</small></td><td class="mono">${money(q.last, q.currency)}<small>${esc(q.price_unit || "")}</small></td><td class="mono ${tone(q.change_percent)}">${percent(q.change_percent)}</td>${metrics ? `<td class="mono">${number(q.metrics?.sma_20)}</td><td class="mono">${q.metrics?.annualized_volatility_20d == null ? "—" : number(q.metrics.annualized_volatility_20d * 100) + "%"}</td>` : ""}<td>${fresh(q)}${q.history_error ? "<small>日线采集异常</small>" : ""}</td><td class="mono">${time(q.exchange_time)}<small>接收 ${time(q.received_at)}</small></td>${watchButtons ? `<td><button class="icon-button" data-action="toggle-watch" data-id="${esc(q.instrument_id)}" aria-label="${state.watch.some((x) => x.instrument_id === q.instrument_id) ? "移除自选" : "加入自选"} ${esc(q.name || q.instrument_id)}">${icon(state.watch.some((x) => x.instrument_id === q.instrument_id) ? "check" : "plus")}</button></td>` : ""}</tr>`).join("")}</tbody></table></div>`;
}
function sessionCards() {
  const destinations = { CN: "#/markets?market=CN", HK: "#/markets?market=HK", US: "#/markets?market=US", FUND: "#/markets?market=FUND", GOLD: "#/gold" };
  const currentMarket = state.route?.name === "gold" ? "GOLD" : state.route?.name === "markets" ? state.route.params.get("market") || "CN" : "";
  const labels = { CN: "A股", HK: "港股", US: "美股", FUND: "基金", GOLD: "黄金" };
  return `<nav class="session-grid" aria-label="市场状态与快捷入口">${state.sessions.map((m) => {
    const active = currentMarket === m.market;
    const phase = phases[m.phase] || m.phase;
    return `<a class="session-card session-link ${active ? "active" : ""}" href="${destinations[m.market] || "#/markets"}" aria-label="${esc(markets[m.market])}，${esc(phase)}，查看行情" ${active ? 'aria-current="page"' : ""}><span class="session-name">${labels[m.market] || esc(markets[m.market])}</span><span class="session-state">${m.phase === "open" ? '<span class="status-dot"></span> ' : ""}${esc(phase)}</span><span class="session-arrow" aria-hidden="true">↗</span></a>`;
  }).join("")}</nav>`;
}
async function renderMarkets(r, signal) {
  const market = r.params.get("market") || "CN",
    q = r.params.get("q") || "",
    offset = Math.max(0, parseInt(r.params.get("offset"), 10) || 0);
  const d = await request(
    `/quotes?browse=true${market === "ALL" ? "" : "&market=" + encodeURIComponent(market)}&q=${encodeURIComponent(q)}&limit=20&offset=${offset}`,
    { signal },
  );
  if (d.total_count && offset >= d.total_count) {
    location.replace(
      "#/markets?market=" +
        encodeURIComponent(market) +
        "&q=" +
        encodeURIComponent(q) +
        "&offset=" +
        Math.floor((d.total_count - 1) / 20) * 20,
    );
    return;
  }
  setPage(
    page(
      heading(
        "市场总览",
        "从行情进入研究，价格与基金净值保留各自口径。",
        `<button class="button" data-action="refresh-market" data-market="${esc(market)}">${icon("refresh")}刷新行情</button><button class="button primary" data-action="ask" data-question="统计${esc(markets[market] || "全部市场")}当前市场状态、行情广度和数据缺口。">${icon("spark")}询问 Agent</button>`,
      ) +
        sessionCards() +
        '<div id="market-index-strip" class="section-gap" aria-live="off"></div>' +
        `<div class="filter-bar"><nav class="route-tabs" aria-label="选择市场">${Object.entries(
          { ALL: "全部", ...markets },
        )
          .map(
            ([id, label]) =>
              `<a class="route-tab ${id === market ? "active" : ""}" href="#/markets?market=${id}" ${id === market ? 'aria-current="page"' : ""}>${label}</a>`,
          )
          .join(
            "",
          )}</nav><form class="search-form" id="market-search" novalidate><label class="sr-only" for="market-query">筛选证券</label><input class="field" id="market-query" name="q" value="${esc(q)}" placeholder="名称或代码" /><button class="icon-button" type="button" data-action="clear-market" aria-label="清空证券筛选" ${q ? "" : "hidden"}>${icon("close")}</button><button class="button">搜索</button></form></div><section class="panel">${quoteTable(d.quotes)}<footer class="table-footer"><span>${d.total_count ? `${number(offset + 1, 0)}–${number(offset + d.count, 0)} / ${number(d.total_count, 0)} 个标的` : "0 个结果"}</span><div class="pager"><a class="button small ${offset === 0 ? "muted" : ""}" href="#/markets?market=${market}&q=${encodeURIComponent(q)}&offset=${Math.max(0, offset - 20)}" ${offset === 0 ? 'aria-disabled="true" tabindex="-1"' : ""}>上一页</a><a class="button small" href="#/markets?market=${market}&q=${encodeURIComponent(q)}&offset=${offset + 20}" ${offset + 20 >= d.total_count ? 'aria-disabled="true" tabindex="-1"' : ""}>下一页</a></div></footer><div class="table-footnote">接收时间不代表行情时间。点击证券名称进入详情；行情源的连接异常可在“数据与模型”中查看。</div></section>`,
    ),
  );
  mountMarketIndices(signal);
}
async function renderWatchlist(r, signal) {
  await refreshWatch(signal);
  const limit = 12,
    pageIndex = Math.min(
      Math.max(0, Math.ceil(state.watch.length / limit) - 1),
      Math.max(0, parseInt(r.params.get("page"), 10) || 0),
    );
  const rows = state.watch.slice(pageIndex * limit, (pageIndex + 1) * limit);
  const results = await Promise.allSettled(
    rows.map((q) =>
      request(
        "/workspace/instruments/" +
          encodeURIComponent(q.instrument_id) +
          "?days=60",
        { signal },
      ),
    ),
  );
  if (signal.aborted) return;
  rows.forEach((q, i) => {
    if (results[i].status === "fulfilled")
      q.metrics = results[i].value.daily_metrics;
  });
  setPage(
    page(
      heading(
        "我的自选",
        "只看你关注的标的，把行情、趋势指标和研究放在一起。",
        `<a class="button" href="#/markets">${icon("search")}发现股票</a><button class="button primary" ${state.watch.length ? "" : 'disabled title="添加自选后可研究"'} data-action="ask" data-question="请结合今天的行情、市场环境和风险，对这些自选标的逐只给出明确的操作建议（买入、加仓、持有、减仓、卖出或观望），并列出依据、数据时点与触发条件：${esc(
          state.watch
            .slice(0, 8)
            .map((x) => x.instrument_id)
            .join("、"),
        )}。">${icon("spark")}今日自选建议</button>`,
      ) +
        `<form class="inline-form section-gap" id="add-watch-form" novalidate><label class="sr-only" for="watch-id">股票名称或代码</label><span class="instrument-search"><input class="field" id="watch-id" name="instrument_id" placeholder="输入股票名称或代码，例如 贵州茅台 / CN:600519" autocomplete="off" data-instrument-picker="select" role="combobox" aria-autocomplete="list" aria-controls="watch-id-results" aria-expanded="false" /><span class="instrument-results" id="watch-id-results" role="listbox" hidden></span></span><button class="button">${icon("plus")}添加自选</button><a class="text-link" href="#/markets">浏览市场</a></form><div class="form-error" id="watch-error" role="alert"></div><section class="panel">${rows.length ? quoteTable(rows, { metrics: true }) : empty("建立你的第一份自选清单", "搜索一只股票，或输入证券代码。添加后将自动采集可用的历史日线。", `<a class="button primary" href="#/markets">${icon("search")}搜索股票</a>`, "star")}<div class="table-footer"><span>${state.watch.length} 个自选 · 指标基于本地真实日线，缺失项显示 —</span>${state.watch.length > limit ? `<div class="pager"><a class="button small" href="#/watchlist?page=${Math.max(0, pageIndex - 1)}" ${pageIndex === 0 ? 'aria-disabled="true" tabindex="-1"' : ""}>上一页</a><a class="button small" href="#/watchlist?page=${pageIndex + 1}" ${(pageIndex + 1) * limit >= state.watch.length ? 'aria-disabled="true" tabindex="-1"' : ""}>下一页</a></div>` : ""}</div></section>`,
    ),
  );
}
async function refreshWatch(signal) {
  state.watch = await request("/watchlist", { signal });
  renderSidebar();
}
async function renderStock(r, signal) {
  const id = canonical(r.id || "");
  const d = await request(
    "/workspace/instruments/" + encodeURIComponent(id) + "?days=500",
    {
      signal,
    },
  );
  const q = d.quote,
    m = d.daily_metrics;
  const tab = r.params.get("tab") || "overview";
  let content = "";
  if (tab === "overview") {
    content = stockOverview(d, r);
  } else if (
    ["profile", "financials", "ownership", "flow", "news"].includes(tab)
  ) {
    content = await dossierTab(id, tab, signal, r.params);
  } else if (tab === "cycles") {
    const cycles = await request(
      "/research/cycles?instrument_id=" + encodeURIComponent(id),
      { signal },
    );
    content = `<div class="actions"><button class="button" data-action="collect-cycle" data-id="${esc(id)}">${icon("refresh")}采集五年日线</button><button class="button primary" data-action="ask" data-question="请基于历史周期工具分析 ${esc(id)} 的阶段趋势、月度季节性和样本风险，不要将历史规律当作预测。">${icon("spark")}分析历史周期</button></div><div class="section-gap">${cycleMarkup(cycles)}</div>`;
  } else if (tab === "documents") {
    const docs = await request("/ai/documents", { signal });
    const rows = docs.filter((x) => x.instrument_id === id);
    content = panel(
      "关联研报与财报",
      rows.length
        ? docRows(rows)
        : empty(
            "还没有关联资料",
            "导入研报或财报时，填写这个标的代码即可。",
            `<a class="button" href="#/documents?instrument=${encodeURIComponent(id)}">导入 ${esc(d.name)} 的资料</a>`,
            "file",
          ),
    );
  } else {
    const rows = state.history.filter(
      (x) =>
        x.question.includes(id) || x.cards?.some((c) => c.instrument_id === id),
    );
    content = panel(
      "相关研究记录",
      rows.length
        ? `<div class="panel-body">${rows.map((x) => `<button class="recent-button" data-action="open-run" data-id="${esc(x.run_id)}">${esc(x.question)} · ${time(x.created_at)}</button>`).join("")}</div>`
        : empty(
            "还没有这只股票的研究",
            "向 Finfreedom 提问，相关研究会保留在这里。",
            `<button class="button" data-action="ask" data-question="请分析 ${esc(id)} 的趋势和主要风险。">开始研究</button>`,
            "chat",
          ),
    );
  }
  setPage(
    page(
      `<a class="text-link" href="#/watchlist">← 返回自选</a><div class="page-heading section-gap"><div><div class="detail-title"><h1 id="page-title">${esc(d.name)}</h1><span class="tag">${esc(id)}</span>${fresh(q)}</div><div class="price-row"><span class="detail-price">${money(q?.last, q?.currency)}</span><span class="mono ${tone(q?.change_percent)}">${percent(q?.change_percent)}</span></div><p>${esc(markets[id.split(":")[0]])} · ${esc(q?.price_unit || "单位未提供")} · 行情 ${time(q?.exchange_time)} · ${esc(q?.provider || "尚无报价")}</p></div><div class="actions"><button class="button" data-action="toggle-watch" data-id="${esc(id)}">${icon(d.watched ? "check" : "star")}${d.watched ? "已在自选" : "加入自选"}</button><button class="button" data-action="pull-stock" data-id="${esc(id)}">${icon("refresh")}拉取日线</button><button class="button primary" data-action="ask" data-question="请分析 ${esc(id)}（${esc(d.name)}）今天适合买入、加仓、持有、减仓、卖出还是观望；先核实行情、趋势、财务和市场环境，引用数据并说明触发与失效条件。">${icon("spark")}询问 Agent</button></div></div>${!q ? '<div class="alert">本地尚无这只证券的行情。加入自选后可请求数据源；可用性以来源返回为准。</div>' : ""}<nav class="route-tabs section-gap" aria-label="个股详情标签">${[
        ["overview", "行情概览"],
        ["profile", "公司资料"],
        ["financials", "财务与分红"],
        ["ownership", "股东"],
        ["flow", "资金"],
        ["news", "公告与新闻"],
        ["documents", "财报与研报"],
        ["cycles", "历史周期"],
        ["history", "研究记录"],
      ]
        .map(
          ([key, label]) =>
            `<a class="route-tab ${tab === key ? "active" : ""}" href="${stockHref(id)}?tab=${key}" ${tab === key ? 'aria-current="page"' : ""}>${label}</a>`,
        )
        .join(
          "",
        )}</nav><div class="section-gap">${content}</div>`,
    ),
  );
  mountStock(d, r, signal);
}
function metric(label, value) {
  return `<div class="metric-line"><span>${esc(label)}</span><strong class="mono">${value}</strong></div>`;
}
let activeSectorRotation = null;
async function renderSectors(r, signal) {
  const [sectorResult, rotationResult] = await Promise.allSettled([
    request(
      "/workspace/sectors" + (r.id ? "?name=" + encodeURIComponent(r.id) : ""),
      { signal, timeout: 24000 },
    ),
    r.id ? Promise.resolve(null) : request("/research/rotation", { signal, timeout: 25000 }),
  ]);
  if (signal.aborted) return;
  const d = sectorResult.status === "fulfilled" ? sectorResult.value : {
    sectors: [], summary: null, constituents: [], flow: null, errors: {},
    state: "unavailable", source: "行业目录", received_at: null,
    last_error: sectorResult.reason.message, flow_note: "行业资金数据暂不可用。",
  };
  activeSectorRotation = rotationResult.status === "fulfilled" ? rotationResult.value : null;
  const summary = d.summary || {},
    flow = d.flow || {};
  const error = d.last_error || Object.values(d.errors || {}).join("；");
  const form = `<form class="inline-form section-gap" id="sector-search" novalidate><label class="sr-only" for="sector-name">行业板块名称</label><input class="field" id="sector-name" name="name" value="${esc(r.id || "")}" placeholder="输入行业名称，例如 半导体、银行" /><button class="button">查看板块</button></form><div class="form-error" id="sector-error" role="alert"></div>`;
  let content = "";
  if (r.id) {
    const rows = d.constituents.map((x) => ({
      instrument_id: "CN:" + String(x["代码"]).padStart(6, "0"),
      name: x["名称"],
      last: x["最新价"],
      change_percent: x["涨跌幅"],
      currency: "CNY",
      freshness: d.freshness,
      provider: d.source,
      received_at: d.received_at,
    }));
    const thsFlow = d.component_sources?.flow === "同花顺";
    const net = thsFlow ? flow["资金净额-元"] : flow["今日主力净流入-净额"] ?? flow["主力净流入-净额"];
    content = `<div class="stat-grid section-gap">${stat("板块涨跌幅", `<span class="${tone(summary["涨跌幅"])}">${percent(summary["涨跌幅"])}</span>`, "板块原始统计")}${stat("上涨 / 下跌", `${number(summary["上涨家数"], 0)} / ${number(summary["下跌家数"], 0)}`, "来源返回值")}${stat(thsFlow ? "行业资金净额" : "行业主力净流入", money(net, "CNY"), thsFlow ? "同花顺口径 · 非北向资金" : "来源成交分类统计 · 非北向资金")}${stat("成分股", number(rows.length, 0), "本次取得的成分股数量")}</div>${panel("行业资金口径", `<div class="panel-body"><p class="field-help">${esc(d.flow_note)}</p>${d.flow ? `<details class="section-gap"><summary>查看来源资金字段</summary><pre class="code-data">${esc(JSON.stringify(d.flow, null, 2))}</pre></details>` : '<p class="field-help">当前没有取得这个板块的资金数值，暂不作资金趋势判断。</p>'}</div>`)}<div class="section-gap">${panel("成分股行情", quoteTable(rows.slice(0, 50)), rows.length > 50 ? "仅展示前 50 个成分股；每只证券可进入个股详情。" : "点击证券名称打开详情")}</div>`;
  } else {
    const catalog = d.sectors.length
      ? `<div class="sector-list section-gap">${d.sectors.map((s) => `<a class="sector-tile" href="${sectorHref(s["板块名称"])}"><div class="sector-top"><h3>${esc(s["板块名称"])}</h3><span class="mono ${tone(s["涨跌幅"])}">${percent(s["涨跌幅"])}</span></div><p>${number(s["上涨家数"], 0)} 家上涨 / ${number(s["下跌家数"], 0)} 家下跌</p></a>`).join("")}</div>`
      : empty(
          "行业数据源暂不可用",
          "可以稍后重试，或输入完整的行业名称；数据源恢复后可查看成分股与资金信息。",
        );
    content = `<div id="rotation-region">${activeSectorRotation ? rotationMarkup(activeSectorRotation, r) : errorPanel(rotationResult.reason || "轮动数据暂不可用")}</div><section class="sector-research-section section-gap" aria-label="行业目录"><details class="sector-catalog-details" ${activeSectorRotation?.rows?.length ? "" : "open"}><summary><strong>完整行业目录 · ${number(d.sectors.length, 0)} 个</strong><span>查看轮动样本之外的行业，进入成分股与资金明细</span></summary>${catalog}</details></section>`;
  }
  setPage(
    page(
      heading(
        r.id ? r.id + "板块" : "板块轮动与资金",
        r.id ? "查看行业表现、资金字段与成分股；返回列表可对照轮动。" : "在同一页查看行业相对强弱、资金表现与完整行业目录。",
        `<button class="button" data-action="refresh-sectors" data-name="${esc(r.id || "")}">${icon("refresh")}刷新板块数据</button><button class="button primary" data-action="ask" data-question="${r.id ? `请分析${esc(r.id)}行业板块的表现、成分股与行业资金统计，并说明数据缺口。` : "请按最新新闻与流动性、大盘环境、行业今日/5日/10日轮动与资金的顺序分析，区分跨窗口排名和跨日变化，列出数据时点、反方证据及风险。"}">${icon("spark")}询问 Agent</button>`,
      ) +
        (r.id ? '<a class="text-link" href="#/sectors">← 全部行业</a>' : "") +
        form +
        (error
          ? `<div class="alert" role="status">${d.state === "unavailable" ? "行业目录或明细暂不可用" : "行业目录或明细部分字段不可用"}。<details><summary>查看连接详情</summary>${esc(error)}</details></div>`
          : "") +
        content +
        `<p class="field-help section-gap">来源：${esc(d.source)} · 接收 ${time(d.received_at)} · 行业划分限 A 股来源覆盖范围。</p>`,
    ),
  );
}
function docRows(docs) {
  return docs
    .map(
      (d) =>
        `<div class="doc-row">${icon("file")}<div class="doc-info"><strong>${esc(d.filename)}</strong><p>${esc(d.instrument_id || "未关联标的")} · ${esc(d.report_period || "报告期未填写")} · ${d.page_count} 页/片段 · ${time(d.imported_at)}</p></div><button class="button small" data-action="ask" data-question="请分析文档 ${esc(d.document_id)}（${esc(d.filename)}），先读取原文，再按观点、依据、财务变化或估值假设、风险和数据缺口归纳，引用页码，不要声称读完未读取的全文。">AI 分析</button><a class="button small" href="${API}/ai/documents/${encodeURIComponent(d.document_id)}/file">原件</a><button class="icon-button" data-action="delete-doc" data-id="${esc(d.document_id)}" data-name="${esc(d.filename)}" aria-label="删除 ${esc(d.filename)}">${icon("close")}</button></div>`,
    )
    .join("");
}
async function renderDocuments(r, signal) {
  const docs = await request("/ai/documents", { signal });
  setPage(
    page(
      heading(
        "研报资料",
        "把材料带进对话。导入后，Finfreedom 可以检索原文并引用页码。",
      ) +
        `<div class="split">${panel("我的资料", docs.length ? docRows(docs) : empty("还没有导入资料", "上传研报、财报或公告，为研究补充原始材料。", "", "file"))}${panel("导入资料", `<form class="panel-body" id="document-form" novalidate data-draft><div class="form-row"><label class="field-label" for="document-file">选择文件</label><input class="field" id="document-file" type="file" name="file" accept=".pdf,.txt,.md,.csv" /><p class="field-help">PDF / TXT / Markdown / CSV · 最大 12 MiB。扫描件暂不支持 OCR。</p></div><div class="form-row"><label class="field-label" for="document-type">资料类型</label><select class="field" id="document-type" name="document_type"><option value="research_report">研报</option><option value="financial_report">财报</option><option value="announcement">公告</option><option value="other">其他</option></select></div><div class="form-row"><label class="field-label" for="document-instrument">关联标的（可选）</label><span class="instrument-search"><input class="field" id="document-instrument" name="instrument_id" value="${esc(r.params.get("instrument") || "")}" placeholder="股票名称或代码" autocomplete="off" data-instrument-picker="select" role="combobox" aria-autocomplete="list" aria-controls="document-instrument-results" aria-expanded="false" /><span class="instrument-results" id="document-instrument-results" role="listbox" hidden></span></span></div><div class="form-row"><label class="field-label" for="document-period">报告期（可选）</label><input class="field" id="document-period" name="report_period" placeholder="例如 2026Q3" /></div><p class="field-help">原件与索引保存在本机。被检索到的片段会发送给你配置的模型。</p><div class="form-error" id="document-error" role="alert"></div><button class="button primary" type="submit">导入资料</button></form>`)}</div>`,
    ),
  );
}
const dateISO = (d) =>
  new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
async function renderResearch(r, signal) {
  const runs = await request("/research/backtests?limit=10", { signal });
  const end = new Date(),
    start = new Date();
  start.setFullYear(start.getFullYear() - 1);
  setPage(
    page(
      heading(
        "策略研究",
        "先研究新闻、流动性和板块轮动，再制定候选、仓位及退出规则。",
        `<button class="button" data-action="ask" data-question="设计一个基于新闻、央行流动性、大盘状态和行业相对强弱的轮动模拟策略：先调对应工具，再提出候选范围、调仓频率、仓位、退出规则、交易成本与样本外验证要求，不虚构回测收益。">${icon("spark")}研究板块轮动策略</button>`,
      ) +
        panel(
          "轮动策略研究链路",
          `<div class="panel-body"><p class="field-help">新闻/政策流动性 → 大盘环境 → 行业相对强弱与资金 → 候选个股 → 模拟仓位与退出。轮动观察标签尚未经过策略收益验证。</p><div class="actions section-gap"><a class="button primary" href="#/sectors">板块轮动与资金</a><a class="button" href="#/news">财经快讯</a><a class="button" href="#/liquidity">央行流动性</a><a class="button" href="#/indices">大盘与指数</a></div></div>`,
        ) +
        `<div class="split section-gap">${panel("SMA 趋势基线", `<form class="panel-body" id="backtest-form" novalidate data-draft><div class="form-row"><label class="field-label" for="backtest-instrument">研究标的</label><span class="instrument-search"><input class="field" id="backtest-instrument" name="instrument_id" value="${esc(r.params.get("instrument") || "")}" placeholder="股票名称或代码" autocomplete="off" data-instrument-picker="select" role="combobox" aria-autocomplete="list" aria-controls="backtest-instrument-results" aria-expanded="false" /><span class="instrument-results" id="backtest-instrument-results" role="listbox" hidden></span></span></div><div class="form-grid"><div class="form-row"><label class="field-label" for="backtest-start">开始日期</label><input class="field" id="backtest-start" name="start" type="date" value="${dateISO(start)}" /></div><div class="form-row"><label class="field-label" for="backtest-end">结束日期</label><input class="field" id="backtest-end" name="end" type="date" value="${dateISO(end)}" /></div><div class="form-row"><label class="field-label" for="backtest-fast">快均线周期</label><input class="field" id="backtest-fast" name="fast_window" type="number" value="20" min="2" max="250" /></div><div class="form-row"><label class="field-label" for="backtest-slow">慢均线周期</label><input class="field" id="backtest-slow" name="slow_window" type="number" value="50" min="3" max="500" /></div></div><p class="field-help">信号在下一根日线生效 · 手续费 10bp + 滑点 5bp · 非复权</p><div class="form-error" id="backtest-error" role="alert"></div><div class="inline-form"><button class="button" type="button" data-action="pull-backtest">拉取区间日线</button><button class="button primary">运行回测</button></div><div class="section-gap" id="backtest-result"></div></form>`)}${panel("最近实验", runs.length ? `<div class="panel-body">${runs.map((x) => `<div class="provider-item section-gap"><a class="stock-link" href="${stockHref(x.instrument_id)}">${esc(x.instrument_id)}</a><p>${esc(x.strategy_id)} · 策略收益 ${percent(x.metrics.total_return * 100)}</p><p>最大回撤 ${percent(x.metrics.max_drawdown * 100)} · ${time(x.created_at)}</p></div>`).join("")}</div>` : empty("还没有回测记录", "准备足够的日线数据后开始实验。", "", "flask"))}</div>`,
    ),
  );
}
function paperUI() {
  return {
    setPage,
    page,
    heading,
    panel,
    busy,
    formError,
    renderRoute,
    accounts: () => state.accounts,
    setAccounts: (accounts) => (state.accounts = accounts),
    clearDraft: (form) => state.forms.delete(draftKey(form)),
    signal: () => state.controller.signal,
    lastReceipt: state.lastReceipt,
    manualSnapshot: () =>
      `<details class="section-gap"><summary>记录外部账户手工快照</summary><section class="panel section-gap"><div class="panel-header"><h2>记录一份账户快照</h2><span class="tag">手工录入</span></div><form class="panel-body" id="manual-account-form" novalidate data-draft><div class="form-grid"><div class="form-row"><label class="field-label" for="manual-label">账户名称</label><input class="field" id="manual-label" name="label" placeholder="我的投资账户" /></div><div class="form-row"><label class="field-label" for="manual-currency">币种</label><select class="field" id="manual-currency" name="currency"><option>CNY</option><option>USD</option><option>HKD</option></select></div><div class="form-row"><label class="field-label" for="manual-cash">现金余额</label><input class="field" id="manual-cash" name="cash" type="number" min="0" step="0.01" /></div><div class="form-row"><label class="field-label" for="manual-positions">持仓 JSON（可选）</label><textarea class="field resize-none" id="manual-positions" name="positions" placeholder='[{"instrument_id":"CN:600519","quantity":100,"currency":"CNY"}]'></textarea></div></div><div class="form-error" id="manual-error" role="alert"></div><button class="button primary">保存账户快照</button></form></section></details>`,
  };
}
async function renderTrading(r, signal) {
  if (r.params.get("source") === "futu") return renderFutuPaper(r, signal, paperUI());
  return r.params.get("tab") === "orders"
    ? renderPaperOrders(r, signal, paperUI())
    : renderPaperAccounts(r, signal, paperUI());
}
function futuStateText(futu) {
  return !futu?.enabled ? '未启用' : futu.connected ? '行情已连接' : futu?.opend_reachable ? 'OpenD 已登录 · 等待行情' : '等待 OpenD 登录';
}
function memoryRetentionMarkup(settings) {
  if (settings.error) return panel('记忆保留期限', `<div class="panel-body"><p class="alert error" role="alert">设置加载失败：${esc(settings.error)}</p><button class="button small" data-action="refresh-memory-settings">重试</button></div>`);
  return `<section class="panel memory-settings" id="memory-settings"><div class="panel-header"><div><h2>记忆保留期限</h2><p>为当前账户设置原始会话和归档记忆的保存时间。</p></div></div><div class="panel-body"><form id="memory-retention-form" class="memory-retention-form" novalidate><label class="field-label" for="session-retention">会话原文保留天数 <input class="field" id="session-retention" type="number" min="1" max="30" inputmode="numeric" value="${number(settings.session_days, 0)}" aria-describedby="session-retention-help memory-form-error"></label><small id="session-retention-help" class="field-help">1–30 天 · 当前最早可读日 ${esc(settings.earliest_session_day || '暂无')}</small><label class="field-label" for="archive-retention">归档记忆保留天数 <input class="field" id="archive-retention" type="number" min="1" max="365" inputmode="numeric" value="${number(settings.archive_days, 0)}" aria-describedby="archive-retention-help memory-form-error"></label><small id="archive-retention-help" class="field-help">1–365 天 · 当前最早日报 ${esc(settings.earliest_archive_day || '暂无')} · 短期记忆最多 30 天</small><p class="field-help memory-retention-warning">缩短期限后，超过新期限的内容会立即清理。归档日报和可编辑的 Markdown 文件请在 AI 投研聊天页打开「投资记忆」。</p><p id="memory-form-error" class="field-help" role="alert"></p><button type="button" class="button primary" data-action="save-memory-settings">保存保留期限</button></form>${state.legacyChatSessions.length ? `<p class="field-help">本机浏览器还有 ${state.legacyChatSessions.length} 个旧会话。只有你选择导入后，才会进入服务端记忆。</p><button class="button small" data-action="import-legacy-sessions">导入旧会话</button>` : ''}</div></section>`;
}
async function renderSettings(_route, signal = state.controller?.signal) {
  if (futuStatusTimer) clearInterval(futuStatusTimer);
  if (state.route?.params?.get('section') === 'memory') {
    const settings = await request('/ai/memory/settings', { signal }).catch((error) => ({ error: error.message }));
    if (signal?.aborted) return;
    setPage(page(heading('记忆保留期限', '此设置属于当前账户，在这里管理聊天原文与归档记忆的保留时间。', '<a class="button small" href="#/memory">打开投资记忆</a>') + memoryRetentionMarkup(settings)));
    return;
  }
  const s = state.status || {};
  const futu = await request('/providers/futu/status').catch(() => null);
  const extensions = await request('/agent/extensions', { signal }).catch((error) => ({ skills: [], mcp: [], error: error.message }));
  if (signal?.aborted) return;
  const futuState = futuStateText(futu);
  setPage(
    page(
      heading("数据与模型", "查看 Agent 配置与市场数据源的实际连接状态。") +
        `<div class="split">${panel("研究模型", `<div class="panel-body"><span class="tag ${s.enabled ? "ready" : "amber"}">${s.enabled ? "配置与运行时就绪" : s.configuration_state === "invalid" ? "配置无效" : "等待配置"}</span><h2 class="section-gap">${esc(s.primary_model || "连接你的 AI 模型")}</h2><p class="field-help section-gap">在项目根目录 .env 配置模型服务，然后重启本地服务。密钥只保留在服务端。</p><pre class="code-data section-gap">MODEL_CONFIG_JSON='[{"provider":"openai","model":"你的模型名","base_url":"https://你的服务/v1","api_key_env":"AI_MODEL_API_KEY"}]'\nPRIMARY_MODEL=你的模型名\nAI_MODEL_API_KEY=你的密钥</pre><p class="field-help section-gap">模型需支持工具调用。Agent 可查行情、指标、行业板块、财务摘要、基金披露、资料与回测。</p></div>`)}${panel("工作空间", `<div class="panel-body">${metric("运行方式", "本地单用户")}${metric("资产记录", "真实持仓账本")}${metric("网页交易", "富途接入 · 默认关闭实盘发送")}${metric("资料存储", "本机 MySQL")}<p class="field-help section-gap">公共数据源可能延迟或失效。你可以继续查看缓存数据，界面会保留来源和时间。</p></div>`)}</div><div class="section-gap">${panel("市场视图配色", `<div class="panel-body"><p class="field-help">A股视图采用 Lobster 深蓝底与珊瑚红强调，红涨绿跌；美股视图采用 OG 石板灰底与柔绿交互色，绿涨红跌。持仓盈亏和收益率随视图着色，错误提示保持警示色。选择保存在本机浏览器。</p><div class="palette-options section-gap" role="group" aria-label="市场视图配色"><button type="button" class="palette-option" data-action="set-market-palette" data-palette="cn" aria-pressed="${marketPalette === "cn"}"><span class="palette-example" aria-hidden="true"><i></i><i></i></span>A股视图 · Lobster · 红涨绿跌</button><button type="button" class="palette-option" data-action="set-market-palette" data-palette="us" aria-pressed="${marketPalette === "us"}"><span class="palette-example" aria-hidden="true"><i></i><i></i></span>美股视图 · OG · 绿涨红跌</button></div></div>`)}</div><div class="section-gap">${panel("富途行情 · 本机 OpenD", `<div class="panel-body"><span id="futu-state" class="tag ${futu?.connected ? "accent" : "amber"}">${esc(futuState)}</span><p id="futu-detail" class="field-help section-gap">${futu?.connected ? `最近收到 ${number(futu.last_quote_count, 0)} 条行情 · ${time(futu.last_success)}` : esc(futu?.last_error || '尚未收到富途行情')}</p><p class="field-help section-gap">启动项目时会自动拉起富途 OpenD。点击下方按钮可切换到富途官方登录窗口；完成登录后返回本页查看行情状态。</p><p id="futu-port" class="field-help section-gap">本机 API 端口 127.0.0.1:${number(futu?.opend_port || 11111, 0)} · ${futu?.opend_reachable ? "已监听" : "未监听"}</p><p class="field-help">网页不接收富途密码、验证码或交易密码；交易账户发现与行情分开配置，实盘发送默认关闭。</p>${futu?.market_errors && Object.keys(futu.market_errors).length ? `<p class="field-help section-gap">市场状态：${Object.entries(futu.market_errors).map(([m,e]) => esc(m + ' ' + e)).join('；')}</p>` : ''}<div class="actions section-gap"><button class="button small primary" data-action="open-futu-login" ${futu?.enabled ? "" : "disabled"}>打开富途 OpenD 登录窗口</button><button class="button small" data-action="refresh-futu-status">刷新连接状态</button><a class="text-link" href="https://openapi.futunn.com/futu-api-doc/quick/opend-base.html" target="_blank" rel="noopener noreferrer">官方安装说明 ↗</a></div></div>`)}</div><div class="section-gap">${panel("市场数据源", `<div class="panel-body provider-list">${state.providers.map((p) => `<article class="provider-item"><div><strong>${esc(p.market_name)}</strong><span class="tag ${p.state === "connected" ? "accent" : "amber"}">${esc({ connected: "已拉取", partial: "部分可用", stale: "缓存过期", error: "连接异常", refreshing: "请求中", waiting: "等待" }[p.state] || p.state)}</span></div><p>${esc(p.provider)} · ${esc(p.endpoint)} · ${number(p.quote_count, 0)} 条记录</p><p>最近接收 ${time(p.last_success)}</p>${p.last_error ? `<details class="section-gap"><summary>查看错误详情</summary><p>${esc(p.last_error)}</p></details>` : ""}<button class="button small section-gap" data-action="refresh-market" data-market="${esc(p.market)}">重新请求</button></article>`).join("")}</div>`)}</div>`,
    ),
  );
  const content = document.querySelector('#page .content-page');
  if (content) content.insertAdjacentHTML('beforeend', extensions.error
    ? `<div class="alert error section-gap" role="alert">扩展配置加载失败：${esc(extensions.error)}</div>`
    : extensionsMarkup(extensions));
  if (!extensions.error) mountExtensions(() => renderSettings());
  syncMarketPaletteControls();
  futuStatusTimer = setInterval(async () => {
    if (signal?.aborted || state.route?.name !== 'settings') {
      clearInterval(futuStatusTimer);
      futuStatusTimer = null;
      return;
    }
    const latest = await request('/providers/futu/status', { timeout: 5000 }).catch(() => null);
    if (!latest || signal?.aborted) return;
    const badge = document.getElementById('futu-state');
    const detail = document.getElementById('futu-detail');
    const port = document.getElementById('futu-port');
    if (badge) {
      badge.textContent = futuStateText(latest);
      badge.className = `tag ${latest.connected ? 'accent' : 'amber'}`;
    }
    if (detail) detail.textContent = latest.connected
      ? `最近收到 ${number(latest.last_quote_count, 0)} 条行情 · ${time(latest.last_success)}`
      : latest.last_error || '尚未收到富途行情';
    if (port) port.textContent = `本机 API 端口 127.0.0.1:${number(latest.opend_port || 11111, 0)} · ${latest.opend_reachable ? '已监听' : '未监听'}`;
  }, 5000);
  signal?.addEventListener('abort', () => clearInterval(futuStatusTimer), { once: true });
}
async function renderRoute() {
  if (!getIdentity() || getIdentity().setup_required) return;
  const legacy = (location.hash.slice(1) || '').split('?')[0];
  if (["/trading", "/accounts", "/account", "/orders"].includes(legacy)) {
    const query = location.hash.includes('?') ? location.hash.slice(location.hash.indexOf('?')) : '';
    history.replaceState(null, '', '#/paper' + (legacy === '/orders' ? (query ? query + '&tab=orders' : '?tab=orders') : query));
  }
  const r = route();
  const samePage = state.route?.name === r.name && r.name !== "chat";
  if (samePage && r.name === "sectors" && !r.id && !state.route.id && activeSectorRotation && state.currentHash !== location.hash) {
    const oldOther = [...state.route.params].filter(([key]) => !["phase", "page"].includes(key)).sort().toString();
    const newOther = [...r.params].filter(([key]) => !["phase", "page"].includes(key)).sort().toString();
    const region = $("#rotation-region");
    if (oldOther === newOther && region) {
      region.innerHTML = rotationMarkup(activeSectorRotation, r);
      state.route = r;
      state.currentHash = location.hash;
      return;
    }
  }
  if (samePage && state.route.id === r.id && ["indices", "stocks"].includes(r.name) && (r.name === "indices" || (r.params.get("tab") || "overview") === "overview") && (state.route.params.get("tab") || "overview") === (r.params.get("tab") || "overview")) {
    const oldOther = [...state.route.params].filter(([key]) => !["period", "range"].includes(key)).sort().toString();
    const newOther = [...r.params].filter(([key]) => !["period", "range"].includes(key)).sort().toString();
    if (state.currentHash !== location.hash && oldOther === newOther && updateChartRoute(r)) {
      state.route = r;
      state.currentHash = location.hash;
      return;
    }
  }
  if (
    state.currentHash &&
    state.route?.name === "documents" &&
    r.name !== "documents" &&
    $("#document-file")?.files?.length
  ) {
    const okay = await confirmDialog(
      "离开资料导入？",
      "<p>选中的文件还没有导入。离开后需要重新选择文件，已填写的文本会保留。</p>",
      "离开页面",
    );
    if (!okay) {
      history.replaceState(null, "", state.currentHash);
      return;
    }
  }
  cleanupPaper();
  cleanupContext();
  cleanupIndices();
  rememberForm();
  state.controller?.abort();
  state.controller = new AbortController();
  const version = ++state.version;
  state.route = r;
  state.currentHash = location.hash || "#/chat";
  state.patchPage = samePage;
  renderUtilityRail();
  const routeTitle = r.name === "settings" && r.params.get("section") === "memory" ? "记忆保留期限" : titles[r.name] || "页面不存在";
  $("#route-label").textContent = routeTitle;
  const calendarLink = $("#topbar-calendar");
  if (r.name === "calendar") calendarLink.setAttribute("aria-current", "page");
  else calendarLink.removeAttribute("aria-current");
  document.title = `${r.name === "stocks" && r.id ? r.id : routeTitle} — Finfreedom`;
  $("#page").classList.toggle("chat-mode", r.name === "chat");
  if (!samePage) {
    renderSidebar();
    document.querySelectorAll("dialog[open]").forEach((d) => d.close());
  }
  if (r.name === "chat") {
    renderChat();
    $("#page").focus({ preventScroll: true });
    return;
  }
  if (!samePage) {
    $("#page-scroll").scrollTop = 0;
    setPage(
      loading(
        r.name === "sectors"
          ? "正在请求行业数据源，最多等待 20 秒…"
          : "正在读取研究数据…",
      ),
    );
  }
  const signal = state.controller.signal;
  try {
    const renderers = {
      calendar: async (r, signal) => {
        const html = await renderCalendarPage(r, state.accounts);
        if (signal.aborted) return;
        setPage(html);
        const date =
          r.params.get("date") || new Date().toLocaleDateString("en-CA");
        mountCalendar(
          date,
          r.params.get("account") || state.accounts[0]?.account_id || "",
          r.params.get("view") || "month",
        );
      },
      markets: renderMarkets,
      gold: (r, signal) => renderGold(r, signal, { setPage, page, heading }),
      news: (r, signal) => renderNews(r, signal, paperUI()),
      liquidity: (r, signal) => renderLiquidity(r, signal, paperUI()),
      indices: (r, signal) => renderIndices(r, signal, paperUI()),
      flows: (r, signal) => renderFlows(r, signal, paperUI()),
      funds: (r, signal) => renderFunds(r, signal, paperUI()),
      watchlist: renderWatchlist,
      stocks: renderStock,
      sectors: renderSectors,
      documents: renderDocuments,
      research: renderResearch,
      holdings: (r, signal) => renderHoldings(r, signal, { setPage, page, heading }),
      paper: renderTrading,
      live: (r, signal) => renderLive(r, signal, paperUI()),
      settings: renderSettings,
      memory: (r, signal) => renderWikiPage(r, signal, { setPage, page, heading }),
      glossary: async (r, signal) => {
        const glossary = await renderGlossaryPage(r, signal, { setPage, page, heading });
        if (!signal.aborted && glossary) state.glossary = glossary;
      },
      security: async (r, signal) => {
        const html = await renderSecurityPage();
        if (signal.aborted) return;
        setPage(html);
        mountSecurityPage(renderRoute);
      },
    };
    if (renderers[r.name]) await renderers[r.name](r, signal);
    else
      setPage(
        page(
          heading("这个页面不存在", "通过导航回到投研对话或市场总览。") +
            '<a class="button primary" href="#/chat">返回对话</a>',
        ),
      );
    if (version !== state.version) return;
    if (!samePage) $("#page").focus({ preventScroll: true });
  } catch (error) {
    if (signal.aborted) return;
    if (samePage) {
      state.patchPage = false;
      notify("当前区域更新未完成：" + error.message, "error");
      return;
    }
    setPage(
      page(
        heading(titles[r.name] || "读取失败", "连接未完成，导航仍可使用。") +
          errorPanel(error),
      ),
    );
  }
}
let orderKey = null;
function formError(id, message, input) {
  const el = $("#" + id);
  if (el) {
    el.textContent = message;
    el.setAttribute("role", "alert");
  }
  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-describedby", id);
    input.focus();
  }
}
async function busy(form, fn) {
  const submit = form.querySelector('button[type="submit"],button:not([type])');
  if (submit?.disabled) return;
  if (submit) {
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
  }
  form.dataset.busy = "true";
  try {
    await fn();
  } finally {
    delete form.dataset.busy;
    if (submit) {
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
    }
  }
}
let composing = false;
document.addEventListener("compositionstart", () => {
  composing = true;
});
document.addEventListener("compositionend", () => {
  composing = false;
});
document.addEventListener("submit", async (e) => {
  const form = e.target;
  if (!(form instanceof HTMLFormElement)) return;
  e.preventDefault();
  if (composing) return;
  if (form.id === 'glossary-edit-form') {
    await handleGlossaryAction({ dataset: { action: 'glossary-submit' } }, {
      state,
      refresh: async () => { state.glossary = await loadGlossary(); if (state.route?.name === 'glossary') await renderRoute(); else updateMessages(false); },
      sendChat,
    });
    return;
  }
  if (await handleHoldingsSubmit(form, renderRoute, formError)) return;
  const values = Object.fromEntries(new FormData(form));
  if (handleCalendarSubmit(form, values)) return;
  if (await handlePaperSubmit(form, values, paperUI())) {
    if (form.id === "paper-ai-form") focusRailCard("trading");
    return;
  }
  if (await handleFutuPaperSubmit(form, values, paperUI())) return;
  if (await handleLiveSubmit(form, values, paperUI())) return;
  if (await handleResearchSubmit(form, values, paperUI())) return;
  if (await handleContextSubmit(form, values)) return;
  if (form.id === "global-search") {
    location.hash =
      "/markets?market=ALL&q=" + encodeURIComponent(values.query.trim());
    return;
  }
  if (form.id === "market-search") {
    location.hash =
      "/markets?market=" +
      (state.route.params.get("market") || "CN") +
      "&q=" +
      encodeURIComponent(values.q.trim());
    return;
  }
  if (form.id === "chat-form") {
    sendChat();
    return;
  }
  if (form.id === "sector-search") {
    if (!values.name.trim()) {
      formError("sector-error", "请输入明确的行业板块名称", $("#sector-name"));
      return;
    }
    location.hash = "/sectors/" + encodeURIComponent(values.name.trim());
    return;
  }
  if (form.id === "add-watch-form") {
    let id;
    try {
      id = await resolveInstrument($("#watch-id"));
    } catch (error) {
      formError("watch-error", error.message, $("#watch-id"));
      return;
    }
    await busy(form, async () => {
      try {
        await request("/watchlist", {
          method: "POST",
          body: { instrument_id: id },
        });
        notify("已添加自选，将自动采集可用日线");
        await refreshShell();
        focusRailCard("watchlist");
        renderRoute();
      } catch (error) {
        formError("watch-error", error.message, $("#watch-id"));
      }
    });
    return;
  }
  if (form.id === "document-form") {
    const file = $("#document-file").files[0];
    if (!file) {
      formError("document-error", "请选择需要导入的资料", $("#document-file"));
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      formError(
        "document-error",
        "文件最大 12 MiB，请选择较小的文件",
        $("#document-file"),
      );
      return;
    }
    if (values.instrument_id.trim()) {
      try {
        const id = await resolveInstrument($("#document-instrument"));
        form.elements.instrument_id.value = id;
      } catch (error) {
        formError("document-error", error.message, $("#document-instrument"));
        return;
      }
    }
    await busy(form, async () => {
      try {
        await request("/ai/documents", {
          method: "POST",
          body: new FormData(form),
          timeout: 60000,
        });
        form.reset();
        state.forms.delete(draftKey(form));
        notify("资料已导入，可在对话中检索");
        renderRoute();
      } catch (error) {
        formError("document-error", error.message);
      }
    });
    return;
  }
  if (form.id === "backtest-form") {
    let instrumentId;
    try {
      instrumentId = await resolveInstrument($("#backtest-instrument"));
    } catch (error) {
      formError("backtest-error", error.message, $("#backtest-instrument"));
      return;
    }
    await busy(form, async () => {
      try {
        const body = {
          ...values,
          instrument_id: instrumentId,
          fast_window: Number(values.fast_window),
          slow_window: Number(values.slow_window),
          fee_bps: 10,
          slippage_bps: 5,
        };
        const d = await request("/research/backtests", {
          method: "POST",
          body,
        });
        $("#backtest-error").textContent = "";
        $("#backtest-result").innerHTML =
          `<div class="stat-grid">${stat("策略收益", percent(d.metrics.total_return * 100))}${stat("买入持有", percent(d.metrics.benchmark_buy_hold_return * 100))}${stat("最大回撤", percent(d.metrics.max_drawdown * 100))}${stat("夏普比率", number(d.metrics.sharpe_ratio))}</div><p class="field-help">${esc(d.run_id)} · ${d.metrics.observations} 日 · ${esc(d.dataset_version)}</p><button type="button" class="button section-gap" data-action="ask" data-question="请解释 ${esc(d.instrument_id)} 的 SMA 回测风险，研究记录 ${esc(d.run_id)}，不要预测未来收益。">${icon("spark")}让 Agent 解释</button>`;
        notify("历史回测已完成");
      } catch (error) {
        formError("backtest-error", error.message);
      }
    });
    return;
  }
  if (form.id === "manual-account-form") {
    if (!values.label.trim()) {
      formError("manual-error", "请输入账户名称", $("#manual-label"));
      return;
    }
    let positions;
    try {
      positions = values.positions.trim() ? JSON.parse(values.positions) : [];
      if (!Array.isArray(positions)) throw Error();
    } catch {
      formError(
        "manual-error",
        "持仓需要是 JSON 数组；也可以留空。",
        $("#manual-positions"),
      );
      return;
    }
    if (values.cash === "" || Number(values.cash) < 0) {
      formError("manual-error", "请输入有效的非负现金余额", $("#manual-cash"));
      return;
    }
    await busy(form, async () => {
      try {
        await request("/accounts/manual", {
          method: "POST",
          body: {
            label: values.label,
            currency: values.currency,
            cash: Number(values.cash),
            positions,
          },
        });
        state.forms.delete(draftKey(form));
        form.reset();
        notify("账户快照已保存");
        await refreshShell();
        renderRoute();
      } catch (error) {
        formError("manual-error", error.message);
      }
    });
    return;
  }
  if (form.id === "order-form") {
    let instrumentId;
    try {
      instrumentId = await resolveInstrument($("#order-instrument"));
    } catch (error) {
      formError("order-error", error.message, $("#order-instrument"));
      return;
    }
    const body = {
      ...values,
      instrument_id: instrumentId,
      quantity: Number(values.quantity),
    };
    if (body.type !== "limit") delete body.limit_price;
    else body.limit_price = Number(body.limit_price);
    if (!body.quantity) {
      formError(
        "order-error",
        "请填写大于零的数量",
        $("#order-quantity"),
      );
      return;
    }
    await busy(form, async () => {
      try {
        const d = await request("/paper/orders/preview", {
          method: "POST",
          body,
        });
        const yes = await confirmDialog(
          "确认这笔模拟订单",
          `<p>以下估算基于当前可用报价，确认时会再次校验行情与账户。</p><dl><dt>标的 / 方向</dt><dd>${esc(body.instrument_id)} / ${body.side === "buy" ? "买入" : "卖出"}</dd><dt>数量</dt><dd>${number(body.quantity, 0)}</dd><dt>估算金额</dt><dd>${money(d.estimated_notional, d.currency)}</dd><dt>估算费用</dt><dd>${money(d.estimated_fee, d.currency)}</dd><dt>行情来源</dt><dd>${esc(d.quote_provider)}</dd><dt>行情时间</dt><dd>${time(d.quote_time)}</dd><dt>模拟撮合</dt><dd>${d.would_fill_at_observed_quote ? "当前报价预计成交" : "等待限价触发"}</dd></dl><p>订单只写入本地模拟账本。</p>`,
          "确认模拟下单",
        );
        if (!yes) return;
        const signature = JSON.stringify(body);
        if (!orderKey || orderKey.signature !== signature)
          orderKey = { signature, key: crypto.randomUUID() };
        const order = await postOrder(body, orderKey.key);
        orderKey = null;
        $("#order-error").textContent = "";
        state.lastReceipt = `${order.order_id} · ${order.status} · 本地模拟账本`;
        $("#order-receipt").textContent = state.lastReceipt;
        notify("模拟订单已提交");
        await refreshShell();
        focusRailCard("trading");
        renderRoute();
      } catch (error) {
        formError("order-error", error.message);
      }
    });
    return;
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "session-query") {
    state.sessionQuery = e.target.value;
    const results = $("#session-results");
    if (results) {
      results.innerHTML = sessionListMarkup();
      results.scrollTop = 0;
    }
  }
  if (e.target.id === "global-query")
    $(".search-clear").hidden = !e.target.value;
  if (e.target.id === "market-query")
    $("[data-action=clear-market]").hidden = !e.target.value;
  if (e.target.matches("input,textarea")) {
    e.target.removeAttribute("aria-invalid");
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === 'holdings-screenshot') {
    handleHoldingsScreenshot(e.target.files[0]);
    return;
  }
  if (e.target.id !== "calendar-account") return;
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  if (e.target.value) params.set("account", e.target.value);
  else params.delete("account");
  location.hash = "/calendar?" + params.toString();
});
window.addEventListener("calendar-ai-draft", (event) => {
  const { date, category } = event.detail || {};
  state.calendarDraft = date && category ? { date, category } : null;
  if (!state.calendarDraft) return;
  ask(`请为我的交易日历起草一份「${category}」，对应日期是 ${date}。结合我关注的市场和可读取的数据，给出简明、可执行的记录草稿；区分已知事实与建议，未知数据请标明。不要声称已保存，等待我确认后再加入日历。`);
});
window.addEventListener("calendar-refresh", () => {
  if (state.route?.name === "calendar") renderRoute();
});
let draggedRailCard = null;
let resizingUtilityRail = false;
document.addEventListener("dragstart", (event) => {
  const card = event.target.closest("[data-rail-card]");
  if (!card) return;
  draggedRailCard = card.dataset.railCard;
  card.classList.add("is-dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", draggedRailCard);
});
document.addEventListener("dragend", (event) => {
  event.target.closest("[data-rail-card]")?.classList.remove("is-dragging");
  draggedRailCard = null;
});
document.addEventListener("dragover", (event) => {
  if (event.target.closest("[data-rail-card]") && draggedRailCard) event.preventDefault();
});
document.addEventListener("drop", (event) => {
  const target = event.target.closest("[data-rail-card]");
  const sourceId = draggedRailCard || event.dataTransfer?.getData("text/plain");
  if (!target || !sourceId || sourceId === target.dataset.railCard) return;
  event.preventDefault();
  const from = state.railCards.indexOf(sourceId), to = state.railCards.indexOf(target.dataset.railCard);
  if (from < 0 || to < 0) return;
  state.railCards.splice(from, 1);
  state.railCards.splice(to, 0, sourceId);
  saveRailPrefs();
  renderUtilityRail();
});
document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".utility-resizer")) return;
  event.preventDefault();
  resizingUtilityRail = true;
  state.railWide = false;
  document.body.classList.add("resizing-utility-rail");
});
window.addEventListener("pointermove", (event) => {
  if (!resizingUtilityRail) return;
  const max = Math.floor(window.innerWidth * 0.5);
  state.railWidth = Math.min(max, Math.max(270, window.innerWidth - event.clientX));
  renderUtilityRail();
});
window.addEventListener("pointerup", () => {
  if (!resizingUtilityRail) return;
  resizingUtilityRail = false;
  document.body.classList.remove("resizing-utility-rail");
  saveRailPrefs();
});
document.querySelector(".skip-link").addEventListener("click", (e) => {
  e.preventDefault();
  $("#page").focus({ preventScroll: true });
});
document.addEventListener("click", (event) => {
  const summary = event.target.closest(".session-day > summary");
  if (summary) sessionDayOpen.set(summary.parentElement.dataset.day, !summary.parentElement.open);
});
document.addEventListener("click", async (e) => {
  const disabled = e.target.closest('a[aria-disabled="true"]');
  if (disabled) {
    e.preventDefault();
    return;
  }
  const button = e.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  if (action.startsWith('glossary-')) {
    try {
      await handleGlossaryAction(button, {
        state,
        refresh: async () => { state.glossary = await loadGlossary(); if (state.route?.name === 'glossary') await renderRoute(); else updateMessages(false); },
        sendChat,
      });
    } catch (error) { notify(error.message || '词条操作未完成，请重试', 'error'); }
    return;
  }
  if (action === "remove-chat-image") {
    const removed = state.pastedImage;
    state.pastedImage = null;
    state.sessionImage = null;
    const preview = document.getElementById("chat-image-preview");
    if (preview) preview.innerHTML = "";
    if (removed?.uploadPromise) removed.uploadPromise.then((uploaded) => {
      if (uploaded && !uploaded.reused) request('/ai/images/' + encodeURIComponent(uploaded.image_id), { method: 'DELETE' }).catch(() => notify('图片移除失败，请删除对应会话以清理原图'));
    });
    document.getElementById("chat-input")?.focus();
    return;
  }
  if (await handlePaperAction(button, paperUI())) {
    if (["paper-run-detail", "paper-refresh-runs", "paper-stop"].includes(action)) focusRailCard("trading");
    return;
  }
  if (await handleFutuPaperAction(button, paperUI())) return;
  if (await handleLiveAction(button, paperUI())) return;
  if (await handleResearchAction(button, paperUI())) return;
  if (await handleCalendarAction(button)) return;
  if (await handleContextAction(button, paperUI())) return;
  if (await handleGoldAction(button, renderRoute)) return;
  if (await handleWikiAction(button, renderRoute)) return;
  if (await handleHoldingsAction(button, renderRoute)) return;
  const id = button.dataset.id;
  if (action === 'refresh-memory-settings') {
    await renderSettings();
    document.querySelector('#memory-settings')?.scrollIntoView({ block: 'start' });
    return;
  }
  if (action === 'save-memory-settings') {
    const sessionInput = $('#session-retention'), archiveInput = $('#archive-retention');
    const sessionDays = Number(sessionInput?.value), archiveDays = Number(archiveInput?.value);
    const error = $('#memory-form-error');
    if (!Number.isInteger(sessionDays) || sessionDays < 1 || sessionDays > 30) {
      error.textContent = '会话原文须保留 1–30 天。';
      sessionInput.setAttribute('aria-invalid', 'true');
      sessionInput.focus();
      return;
    }
    if (!Number.isInteger(archiveDays) || archiveDays < 1 || archiveDays > 365) {
      error.textContent = '归档记忆须保留 1–365 天。';
      archiveInput.setAttribute('aria-invalid', 'true');
      archiveInput.focus();
      return;
    }
    sessionInput.removeAttribute('aria-invalid');
    archiveInput.removeAttribute('aria-invalid');
    error.textContent = '';
    button.disabled = true;
    try {
      await request('/ai/memory/settings', { method: 'PATCH', body: { session_days: sessionDays, archive_days: archiveDays } });
      notify('记忆保留期限已保存；过期内容已清理');
      await renderSettings();
      document.querySelector('#memory-settings')?.scrollIntoView({ block: 'start' });
    } catch (failure) { error.textContent = failure.message; }
    finally { button.disabled = false; }
    return;
  }
  if (action === 'import-legacy-sessions') {
    if (!await confirmDialog('导入旧会话', `<p>仅导入仍在会话保留期内的浏览器聊天。导入后，这些内容会进入每日归档；旧浏览器记录不会自动成为已确认的投资偏好。</p>`, '导入会话')) return;
    button.disabled = true;
    try {
      const sessions = state.legacyChatSessions.map((session) => ({ title: session.title || '旧投研会话', messages: (session.messages || []).filter((message) => !message.management && !privateExtensionText(message.content) && (message.created_at || session.updated_at)).map((message) => ({ role: message.role, content: String(message.content || '').slice(0, 4000), created_at: message.created_at || session.updated_at })) }));
      const result = await request('/ai/sessions/import', { method: 'POST', body: { sessions } });
      if (result.imported_messages > 0) {
        state.legacyChatSessions = [];
        try { localStorage.removeItem(sessionStoreKey()); } catch (_error) { /* Server copy is authoritative. */ }
      }
      notify(`已导入 ${result.imported_messages} 条旧消息`);
      await refreshShell();
      await renderSettings();
    } catch (failure) { notify(failure.message); }
    finally { button.disabled = false; }
    return;
  }
  if (action === "toggle-market-palette" || action === "set-market-palette") {
    setMarketPalette(action === "toggle-market-palette"
      ? marketPalette === "cn" ? "us" : "cn"
      : button.dataset.palette);
    return;
  }
  if (action === "calendar-add-ai") {
    const index = Number(button.dataset.index), message = state.messages[index];
    if (message?.calendarDraft && addAICalendarPlan(message.calendarDraft.date, message.calendarDraft.category, message.content)) {
      message.calendarDraft = null;
      updateMessages(false);
    }
    return;
  }
  if (action === "sign-out") {
    await signOut();
    return;
  }
  if (action === "close-dialog") {
    button.closest("dialog")?.close();
    return;
  }
  if (action === "open-nav") {
    $("#nav-dialog").showModal();
    return;
  }
  if (action === "open-utility") {
    if (window.matchMedia("(min-width: 901px)").matches && route().name === "chat" && !state.railVisible) {
      state.railVisible = true;
      saveRailPrefs();
      renderUtilityRail();
      return;
    }
    $("#utility-dialog-content").innerHTML = utilityRailMarkup();
    $("#utility-dialog").showModal();
    return;
  }
  if (action === "hide-rail") {
    state.railVisible = false;
    saveRailPrefs();
    button.closest("dialog")?.close();
    renderUtilityRail();
    return;
  }
  if (action === "manage-rail") {
    manageRail();
    return;
  }
  if (action === "save-rail") {
    const selected = [...document.querySelectorAll("[data-rail-select]:checked")].map((input) => input.dataset.railSelect);
    state.railCards = [...state.railCards.filter((card) => selected.includes(card)), ...selected.filter((card) => !state.railCards.includes(card))];
    if (!state.railCards.length) state.railCards = ["watchlist"];
    if (!state.railCards.includes(state.expandedRailCard)) state.expandedRailCard = null;
    saveRailPrefs();
    $("#app-dialog").close();
    renderUtilityRail();
    notify("右侧卡片已更新");
    return;
  }
  if (action === "toggle-rail-width") {
    state.railWide = !state.railWide;
    if (state.railWide) state.expandedRailCard = state.expandedRailCard || state.railCards[0] || null;
    saveRailPrefs();
    renderUtilityRail();
    return;
  }
  if (action === "expand-rail-card") {
    state.expandedRailCard = state.expandedRailCard === id ? null : id;
    saveRailPrefs();
    renderUtilityRail();
    return;
  }
  if (action === "hide-rail-card") {
    state.railCards = state.railCards.filter((card) => card !== id);
    if (state.expandedRailCard === id) state.expandedRailCard = null;
    saveRailPrefs();
    renderUtilityRail();
    return;
  }
  if (action === "move-rail-card") {
    const index = state.railCards.indexOf(id);
    const next = index + (button.dataset.direction === "up" ? -1 : 1);
    if (index >= 0 && next >= 0 && next < state.railCards.length) {
      [state.railCards[index], state.railCards[next]] = [state.railCards[next], state.railCards[index]];
      saveRailPrefs();
      renderUtilityRail();
    }
    return;
  }
  if (action === "account-menu") {
    const user = getIdentity()?.user || {};
    showDialog("账户与个人设置", `<div class="account-dialog-profile"><div class="account-menu-avatar">${esc((user.username || "我").slice(0, 1).toUpperCase())}</div><div><strong>${esc(user.username || getIdentity()?.username || "私人空间")}</strong><p>${identitySecurityLabel()}</p></div></div><dl class="account-profile-data"><dt>用户</dt><dd>${esc(user.username || "私人空间")}</dd><dt>工作空间</dt><dd>本地私人投研</dd>${user.user_id || user.id ? `<dt>账户编号</dt><dd>${esc(user.user_id || user.id)}</dd>` : ""}</dl>${identityMenuMarkup()}`);
    return;
  }
  if (action === "clear-global") {
    $("#global-query").value = "";
    $(".search-clear").hidden = true;
    $("#global-query").focus();
    return;
  }
  if (action === "clear-market") {
    const market = state.route.params.get("market") || "CN";
    const input = $("#market-query");
    input.value = "";
    button.hidden = true;
    if (state.route.params.get("q")) {
      location.hash = "/markets?market=" + market;
      requestAnimationFrame(() => $("#market-query")?.focus());
    } else input.focus();
    return;
  }
  if (action === "retry-route") {
    renderRoute();
    return;
  }
  if (action === "new-chat") {
    if (state.sending) return;
    persistChatSession();
    state.messages = [];
    state.glossaryExpanded = false;
    state.draft = "";
    state.pastedImage = null;
    state.sessionImage = null;
    state.accountId = null;
    state.pendingAccountQuestion = null;
    state.activeChatId = null;
    if (state.route.name === "chat") renderChat();
    else location.hash = "/chat";
    return;
  }
  if (action === "ask" || action === "prompt") {
    ask(button.dataset.question);
    return;
  }
  if (action === "retry-chat") {
    const index = Number(button.dataset.index);
    const original = state.messages[index - 1];
    if (original?.imageAttached && !original.imageId && !original.imagePreview) {
      notify('此旧会话的原图未保留，请重新粘贴图片后发送');
      return;
    }
    if (original?.imageAttached && !original.imageId && original.imagePreview) {
      state.pastedImage = { dataUrl: original.imagePreview, filename: 'retry-image.png', size: 0,
        uploadPromise: Promise.resolve(null) };
    }
    sendChat(state.messages[index].question, original?.imageId || null);
    return;
  }
  if (action === "copy-message") {
    try {
      await navigator.clipboard.writeText(
        state.messages[Number(button.dataset.index)].content,
      );
      notify("已复制研究内容");
    } catch {
      notify("复制未完成，请选中文字复制");
    }
    return;
  }
  if (action === "open-run") {
    if (state.sending) {
      notify("请等待当前研究完成");
      return;
    }
    try {
      const d =
        state.history.find((x) => x.run_id === id) ||
        (await request("/ai/research/" + encodeURIComponent(id)));
      state.messages = [
        { role: "user", content: d.question, created_at: d.created_at },
        {
          role: "assistant",
          content: d.answer || "",
          model: d.model,
          evidence: d.evidence,
          cards: d.cards,
          tool_calls: d.tool_calls,
          error: d.error,
          created_at: d.completed_at || d.created_at,
        },
      ];
      state.activeChatId = `history-${d.run_id}`;
      state.sessionImage = null;
      persistChatSession();
      if (state.route.name === "chat") renderChat();
      else location.hash = "/chat";
    } catch (error) {
      notify(error.message);
    }
    return;
  }
  if (action === "open-session") {
    if (state.sending) { notify("请等待当前研究完成"); return; }
    persistChatSession();
    try {
      const listed = state.chatSessions.find((item) => item.id === id);
      const session = listed?.source === 'server'
        ? await request("/ai/sessions/" + encodeURIComponent(id))
        : listed;
      if (!session) throw new Error('会话已不可用，请刷新页面');
      state.activeChatId = session.id;
      state.sessionImage = listed?.source === 'server'
        ? await request('/ai/images/latest?session_id=' + encodeURIComponent(session.id)).catch(() => null)
        : null;
      state.memoryStatus = "ready";
      state.messages = (session.messages || []).map((message) => ({ ...message }));
      state.draft = "";
      if (state.route?.name === "chat") renderChat();
      else location.hash = "/chat";
    } catch (error) { notify(error.message); }
    return;
  }
  if (action === "delete-session") {
    if (state.sending) { notify("请等待当前研究完成"); return; }
    if (!state.serverChatSessions.some((item) => item.id === id)) return;
    if (!await confirmDialog('删除投研会话', '<p>会删除服务端会话及仅由它支持的记忆；受影响日报会重新归档。</p>', '删除会话', true)) return;
    try {
      await request("/ai/sessions/" + encodeURIComponent(id), { method: "DELETE" });
      state.serverChatSessions = state.serverChatSessions.filter((item) => item.id !== id);
      rebuildChatSessions();
      if (state.activeChatId === id) { state.activeChatId = null; state.messages = []; state.sessionImage = null; }
      renderSidebar();
      if (state.route?.name === "chat") renderChat();
      notify("会话及仅由它支持的记忆已删除");
    } catch (error) { notify(error.message); }
    return;
  }
  if (action === "show-evidence" || action === "all-evidence") {
    const msg =
      action === "show-evidence"
        ? state.messages[
            Number(button.closest("[data-message]").dataset.message)
          ]
        : state.messages[Number(button.dataset.index)];
    const rows = (msg?.evidence || []).filter(
      (x) => action !== "show-evidence" || x.evidence_id === id,
    );
    showDialog(
      "研究证据",
      rows.length
        ? rows
            .map(
              (x) =>
                `<h3>${esc(x.evidence_id)} · ${esc(x.title)}</h3><p>${esc(x.source)} · ${time(x.as_of)}</p><pre class="code-data section-gap">${esc(JSON.stringify(x.detail, null, 2))}</pre>`,
            )
            .join("")
        : empty("尚无对应证据", "这条引用未关联到可验证数据。"),
    );
    return;
  }
  if (action === "account-context") {
    state.pendingAccountQuestion = null;
  }
  if (action === "daily-advice") {
    state.pendingAccountQuestion = "请读取我本轮选择的真实持仓账户，结合最新新闻、流动性、大盘、行业与各持仓标的行情，逐只给出今天的操作建议。请区分实际持仓与自选，并结合已登记数量、成本和币种说明仓位风险；逐项注明数据时点、触发条件、失效条件和缺口，缺少关键数据时建议暂不操作。";
    if (state.accountId?.startsWith('personal-')) {
      ask(state.pendingAccountQuestion);
      state.pendingAccountQuestion = null;
      return;
    }
  }
  if (action === "account-context" || action === "daily-advice") {
    try {
      state.accounts = await request("/accounts", { timeout: 12000 });
    } catch (failure) {
      notify(failure.message || "账户列表暂时无法读取");
      return;
    }
    const personalAccounts = state.accounts.filter((a) => a.mode === 'personal');
    showDialog(
      "账户研究上下文",
      `<p>选择“我的持仓”账户后，Agent 会在相关问题中按需通过内置 MCP 读取该账户数据，并标明数据时点。</p>${personalAccounts.length ? `<label class="field-label section-gap" for="context-account">选择账户</label><select id="context-account" class="field"><option value="">不读取账户</option>${personalAccounts.map((a) => `<option value="${esc(a.account_id)}" ${state.accountId === a.account_id ? "selected" : ""}>${esc(a.label)} · ${esc(a.currency)} · ${a.positions?.length || 0} 条持仓</option>`).join("")}</select>` : `<p class="field-help section-gap">尚未登记真实持仓。请先在 <a href="#/holdings">我的持仓</a> 保存账户数据。</p>`}`,
      personalAccounts.length ? `<button class="button primary" data-action="save-account-context">${state.pendingAccountQuestion ? "选择并准备分析" : "保存选择"}</button>` : '',
    );
    return;
  }
  if (action === "save-account-context") {
    const selected = $("#context-account").value || null;
    if (state.pendingAccountQuestion && !selected) {
      notify("请先选择一个已登记的持仓账户");
      return;
    }
    state.accountId = selected;
    const pendingQuestion = state.pendingAccountQuestion;
    state.pendingAccountQuestion = null;
    $("#app-dialog").close();
    if (state.route.name === "chat") renderChat();
    if (pendingQuestion) ask(pendingQuestion);
    notify(state.accountId ? "当前对话允许读取所选账户" : "已关闭账户读取");
    return;
  }
  if (action === "toggle-watch") {
    button.disabled = true;
    try {
      if (state.watch.some((x) => x.instrument_id === id)) {
        await request("/watchlist/" + encodeURIComponent(id), {
          method: "DELETE",
        });
        notify("已移出自选");
      } else {
        await request("/watchlist", {
          method: "POST",
          body: { instrument_id: id },
        });
        notify("已加入自选");
      }
      await refreshShell();
      focusRailCard("watchlist");
      renderRoute();
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "refresh-market") {
    button.disabled = true;
    try {
      const targets =
        button.dataset.market === "ALL"
          ? Object.keys(markets)
          : [button.dataset.market];
      await Promise.all(
        targets.map((market) =>
          request("/refresh/" + market, { method: "POST" }),
        ),
      );
      notify("已请求行情更新，数据源正在处理");
      await refreshShell();
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "open-futu-login") {
    button.disabled = true;
    try {
      const result = await request('/providers/futu/open-login', { method: 'POST', timeout: 8000 });
      notify(result.message);
      await renderSettings();
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "refresh-futu-status") {
    await renderSettings();
    return;
  }
  if (action === "refresh-sectors") {
    button.disabled = true;
    try {
      const name = button.dataset.name;
      const requestedHash = location.hash;
      const tasks = [request(
        "/workspace/sectors?refresh=true" +
          (name ? "&name=" + encodeURIComponent(name) : ""),
        { timeout: 24000 },
      )];
      if (!name) tasks.push(request("/research/rotation?refresh=true", { timeout: 25000 }));
      const results = await Promise.allSettled(tasks);
      if (results.some((result) => result.status === "fulfilled") && location.hash === requestedHash && state.route?.name === "sectors") await renderRoute();
      const failures = results.filter((result) => result.status === "rejected");
      if (failures.length) notify("部分板块数据未能刷新：" + failures.map((result) => result.reason.message).join("；"), "error");
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "pull-stock" || action === "pull-backtest") {
    button.disabled = true;
    try {
      const form = $("#backtest-form"),
        values = form ? Object.fromEntries(new FormData(form)) : {};
      const end = values.end || dateISO(new Date()),
        start = values.start || dateISO(new Date(Date.now() - 366 * 86400000));
      const instrument = id || await resolveInstrument($("#backtest-instrument"));
      if (!instrument.includes(":")) throw Error("请先填写研究标的");
      await request(
        `/bars/pull?instrument_id=${encodeURIComponent(instrument)}&start=${start}&end=${end}`,
        { method: "POST", timeout: 45000 },
      );
      notify("日线数据已保存");
      if (action === "pull-stock") renderRoute();
    } catch (error) {
      if (action === "pull-backtest")
        formError("backtest-error", error.message);
      else notify(error.message);
    } finally {
      button.disabled = false;
    }
    return;
  }
  if (action === "delete-doc") {
    const yes = await confirmDialog(
      "删除这份资料？",
      `<p>将删除「${esc(button.dataset.name)}」的原件和检索片段，并清理历史研究中的相关文档证据。此操作无法撤销。</p>`,
      "删除资料",
      true,
    );
    if (!yes) return;
    try {
      await request("/ai/documents/" + encodeURIComponent(id), {
        method: "DELETE",
      });
      notify("资料与相关证据已删除");
      renderRoute();
    } catch (error) {
      notify(error.message);
    }
    return;
  }
  if (action === "cancel-order") {
    button.disabled = true;
    try {
      await request("/paper/orders/" + encodeURIComponent(id) + "/cancel", {
        method: "POST",
      });
      notify("模拟订单已取消");
      renderRoute();
    } catch (error) {
      notify(error.message);
    } finally {
      button.disabled = false;
    }
  }
});
for (const dialog of document.querySelectorAll("dialog"))
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (
        e.clientX < rect.left ||
        e.clientX > rect.right ||
        e.clientY < rect.top ||
        e.clientY > rect.bottom
      )
        dialog.close();
    }
  });
document.addEventListener("click", (e) => {
  if (
    e.target.closest("#nav-dialog a") ||
    e.target.closest('#app-dialog a[href^="#/"]') ||
    e.target.closest('#utility-dialog a[href^="#/"]')
  )
    e.target.closest("dialog").close();
});
window.addEventListener("hashchange", renderRoute);
window.addEventListener("online", () => {
  if (getIdentity()) {
    notify("连接已恢复");
    refreshShell();
  }
});
$(".mobile-menu").innerHTML = icon("menu");
$(".utility-toggle").innerHTML = icon("grid");
$("#search-icon").innerHTML = icon("search");
$(".topbar-calendar-icon").innerHTML = icon("calendar");
let initializedUI = false;
function startWorkspace() {
  clearHoldingsDraft();
  state.pastedImage = null;
  state.sessionImage = null;
  state.legacyChatSessions = loadChatSessions();
  state.serverChatSessions = [];
  state.history = [];
  rebuildChatSessions();
  state.activeChatId = null;
  renderSidebar();
  renderUtilityRail();
  startCalendarAlarms();
  renderRoute();
  refreshShell().then(() => {
    if (state.route?.name === "markets") renderRoute();
  });
}
document.addEventListener("finch:authenticated", () => {
  if (initializedUI) startWorkspace();
});
document.addEventListener("finch:locked", () => {
  clearHoldingsDraft();
  state.pendingAccountQuestion = null;
  state.pastedImage = null;
  state.sessionImage = null;
  stopCalendarAlarms();
  cleanupPaper();
  cleanupCalendar();
  cleanupContext();
  cleanupIndices();
  state.controller?.abort();
  document.title = "登录 — Finfreedom";
});
document.addEventListener("finch:signed-out", () => {
  clearHoldingsDraft();
  stopCalendarAlarms();
  cleanupPaper();
  cleanupCalendar();
  cleanupContext();
  cleanupIndices();
  state.controller?.abort();
  state.messages = [];
  state.draft = "";
  state.pastedImage = null;
  state.sessionImage = null;
  state.accountId = null;
  state.pendingAccountQuestion = null;
  state.watch = [];
  state.accounts = [];
  state.history = [];
  state.forms.clear();
  state.lastReceipt = null;
  state.status = null;
  $("#sidebar").innerHTML = "";
  $("#mobile-nav").innerHTML = "";
  $("#page").innerHTML = "";
});
async function bootstrapIdentity() {
  try {
    await requireIdentity();
    if (!initializedUI) {
      initializedUI = true;
      startWorkspace();
    }
  } catch (error) {
    const root = $("#identity-root");
    root.textContent = "无法连接身份服务：" + error.message;
    const button = document.createElement("button");
    button.className = "button";
    button.textContent = "重新连接";
    button.onclick = bootstrapIdentity;
    root.append(button);
  }
}
bootstrapIdentity();
setInterval(refreshShell, 60000);
setInterval(() => {
  if (getIdentity() && state.route?.name === 'holdings' && document.visibilityState === 'visible'
      && document.getElementById('holding-editor')?.hidden && document.getElementById('holding-import')?.hidden) {
    renderRoute();
  }
}, 60000);
