import { request } from "./api.js";
import { getIdentity } from "./identity.js";
import { esc, icon, money, percent, tone, notify } from "./ui.js";

const MARKET_NAMES = { CN: "A股", HK: "港股", US: "美股" };
const CATEGORIES = ["日报", "操作策略", "操作日志"];
const SUB_CATEGORIES = ["A股打新", "逆回购", "财报披露", "自定义"];
const HOURS = Array.from({ length: 17 }, (_, i) => `${String(i + 6).padStart(2, "0")}:00`);
let activeAccount = "";
let activeCollapsed = false;
const storageKey = () => `finch.calendar.v2:${getIdentity()?.user?.username || "local"}`;
const emptyStore = () => ({ plans: [], events: [], subscriptions: [], reminders: false });
function readStore() {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey()) || "null") || {};
    return { ...emptyStore(), ...data, plans: data.plans || [], events: data.events || [], subscriptions: data.subscriptions || [] };
  } catch { return emptyStore(); }
}
function writeStore(value) {
  try { localStorage.setItem(storageKey(), JSON.stringify(value)); return true; }
  catch { notify("浏览器未能保存日历内容，请检查本机存储空间", "error"); return false; }
}
function isoLocal(date = new Date()) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`; }
function usOpenBeijingTime() {
  try {
    const zone = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", timeZoneName: "shortOffset" }).formatToParts(new Date()).find(x => x.type === "timeZoneName")?.value || "GMT-5";
    const offset = Number((zone.match(/GMT([+-]\d+)/) || [])[1] || -5);
    const openHour = (9.5 - offset + 8) % 24;
    const close = (16 - offset + 8) % 24;
    const fmt = h => `${String(Math.floor(h)).padStart(2,"0")}:${h % 1 ? "30" : "00"}`;
    return `北京时间 ${fmt(openHour)} 开盘 · ${close < openHour ? "次日 " : ""}${fmt(close)} 收盘`;
  } catch { return "纽约时间 09:30–16:00"; }
}
function fromISO(value) { const [y, m, d] = value.split("-").map(Number); return new Date(y, m - 1, d, 12); }
function safeURL(value) { try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : ""; } catch { return ""; } }
function calendarURL(month, day, view = "month") { return `#/calendar?month=${month}&date=${day}&view=${view}${activeAccount ? `&account=${encodeURIComponent(activeAccount)}` : ""}${activeCollapsed ? "&collapsed=1" : ""}`; }
function planRows(store, date) { return store.plans.filter(x => x.date === date).sort((a,b) => (a.time || "").localeCompare(b.time || "")); }
function eventRows(store, date) { const enabled = new Set(store.subscriptions.filter(x => x.enabled).map(x => x.id)); return store.events.filter(x => x.date === date && (!x.subscriptionId || enabled.has(x.subscriptionId))).sort((a,b) => (a.time || "").localeCompare(b.time || "")); }
function marketDaysMarkup(sessions, date) {
  const row = sessions?.days?.find(x => x.date === date);
  if (!row) return `<p class="field-help">交易所日历未返回这一天。</p>`;
  return `<div class="calendar-market-list">${["CN","HK","US"].map(m => { const x = row[m]; return `<div class="calendar-market-row"><div><span class="calendar-market-dot ${x?.is_open ? "open" : "closed"}"></span><strong>${MARKET_NAMES[m]}</strong></div><span class="calendar-session-state">${x?.is_open ? `${esc(x.open)}–${esc(x.close)} ${m === "US" ? "ET" : "当地时间"}` : "休市"}</span></div>`; }).join("")}</div><p class="field-help calendar-source">交易所日历 · 美股时间为纽约当地时间</p>`;
}
function eventTag(item) { const cls = item.category === "A股打新" ? "ipo" : item.category === "逆回购" ? "repo" : item.category === "财报披露" ? "earnings" : "subscription"; return `<span class="calendar-event ${cls}" title="${esc(item.title)}">${esc(item.title || item.category)}</span>`; }
function dayCell(date, month, selected, store, sessions, pnl, today) {
  const key = isoLocal(date), inMonth = date.getMonth() + 1 === Number(month.slice(5,7));
  const market = sessions?.days?.find(x => x.date === key), openCount = market ? ["CN","HK","US"].filter(m => market[m]?.is_open).length : 0;
  const events = eventRows(store, key), plans = planRows(store, key), value = pnl?.[key];
  const markers = [...events.slice(0,2).map(eventTag), ...plans.slice(0, Math.max(0, 2-Math.min(events.length,2))).map(x => `<span class="calendar-event plan">${esc(x.category === "操作策略" ? "策略" : x.category === "操作日志" ? "日志" : "日报")}</span>`)].join("");
  return `<a class="calendar-day ${inMonth ? "" : "outside"} ${openCount ? "has-open" : ""} ${key === selected ? "selected" : ""} ${key === today ? "today" : ""}" href="${calendarURL(key.slice(0,7),key)}" aria-label="${key}${openCount ? `，${openCount}个市场开市` : "，市场休市"}" ${key === selected ? 'aria-current="date"' : ""}><span class="calendar-day-num">${date.getDate()}</span>${inMonth ? `<span class="calendar-day-markers">${markers || ""}</span><span class="calendar-open-count">${openCount ? `● ${openCount}市开市` : "休市"}</span><span class="calendar-day-pnl ${value?.complete ? (tone(value.day_pnl)) : ""}" data-pnl-date="${key}">${value?.complete ? `${value.day_pnl > 0 ? "+" : ""}${money(value.day_pnl, value.currency)}` : ""}</span>` : ""}</a>`;
}
function monthGridMarkup(month, selected, store, sessions, pnl) {
  const [year, mm] = month.split("-").map(Number), first = new Date(year,mm-1,1,12), offset = (first.getDay()+6)%7, start = new Date(year,mm-1,1-offset,12), today = isoLocal();
  return `<div class="calendar-weekdays" aria-hidden="true">${["一","二","三","四","五","六","日"].map(x=>`<span>${x}</span>`).join("")}</div><div class="calendar-grid">${Array.from({length:42},(_,i)=>{const d=new Date(start);d.setDate(start.getDate()+i);return dayCell(d,month,selected,store,sessions,pnl,today)}).join("")}</div>`;
}
function weekGridMarkup(selected, store, sessions) {
  const day = fromISO(selected), monday = new Date(day); monday.setDate(day.getDate()-((day.getDay()+6)%7));
  const days = Array.from({length:7},(_,i)=>{const d=new Date(monday);d.setDate(monday.getDate()+i);return isoLocal(d)});
  const heads = days.map(date=>`<a class="calendar-week-day ${date===selected?"active":""}" href="${calendarURL(date.slice(0,7),date,"week")}"><strong>${fromISO(date).toLocaleDateString("zh-CN",{weekday:"short"})}</strong><span>${date.slice(5)}</span><small>${["CN","HK","US"].filter(m=>sessions?.days?.find(x=>x.date===date)?.[m]?.is_open).join(" · ") || "休市"}</small></a>`).join("");
  const rows = HOURS.map(hour=>`<div class="calendar-hour-row"><span class="calendar-hour-label">${hour}</span>${days.map(date=>{const plans=planRows(store,date).filter(x=>x.time?.slice(0,2)===hour.slice(0,2)), events=eventRows(store,date).filter(x=>x.time?.slice(0,2)===hour.slice(0,2));return `<div class="calendar-hour-cell" data-calendar-date="${date}" data-calendar-time="${hour}">${events.map(x=>`<div class="calendar-week-event ${x.category=== "A股打新"?"ipo":"subscription"}" title="${esc(x.detail || x.title)}">${esc(x.title)}</div>`).join("")}${plans.map(x=>`<div class="calendar-week-event plan" title="${esc(x.text)}">${esc(x.category)} · ${esc(x.text)}</div>`).join("")}<button type="button" class="calendar-hour-add" data-action="calendar-add-hour" data-date="${date}" data-time="${hour}" aria-label="${date} ${hour} 添加计划">＋</button></div>`}).join("")}</div>`).join("");
  return `<div class="calendar-week-board"><div class="calendar-week-head"><div class="calendar-hour-label">时段</div>${heads}</div>${rows}</div>`;
}
function compactWeekMarkup(selected, store, sessions) {
  const date=fromISO(selected), monday=new Date(date);monday.setDate(date.getDate()-((date.getDay()+6)%7));
  const days=Array.from({length:7},(_,i)=>{const d=new Date(monday);d.setDate(monday.getDate()+i);const key=isoLocal(d),events=eventRows(store,key),plans=planRows(store,key),market=sessions?.days?.find(x=>x.date===key),opens=["CN","HK","US"].filter(m=>market?.[m]?.is_open).length;return `<a class="calendar-compact-day ${key===selected?"selected":""}" href="${calendarURL(key.slice(0,7),key)}" aria-current="${key===selected?"date":"false"}"><span>${fromISO(key).toLocaleDateString("zh-CN",{weekday:"short"})}</span><strong>${Number(key.slice(8,10))}</strong><small>${opens?`${opens} 市开市`:"休市"}</small><div class="calendar-compact-tags">${events.slice(0,2).map(eventTag).join("")}${plans.length?`<span class="calendar-event plan">${plans.length} 项计划</span>`:""}</div><b class="calendar-day-pnl" data-pnl-date="${key}"></b></a>`}).join("");
  return `<div class="calendar-compact-week"><div class="calendar-compact-caption"><strong>本周概览</strong><span>${isoLocal(monday)} — ${isoLocal(new Date(monday.getFullYear(),monday.getMonth(),monday.getDate()+6,12))}</span></div><div class="calendar-compact-days">${days}</div></div>`;
}
function accountSelector(accounts, accountId) {
  return accounts.length ? `<label class="sr-only" for="calendar-account">选择模拟账户</label><select class="field calendar-account-select" id="calendar-account"><option value="">选择模拟盘</option>${accounts.map(x=>`<option value="${esc(x.account_id)}" ${x.account_id===accountId?"selected":""}>${esc(x.label)} · ${esc(x.market_name||x.market)}</option>`).join("")}</select>` : `<p class="field-help">还没有模拟账户，可先到“账户与模拟盘”开户。</p>`;
}
function sourceLink(url, label="查看来源") { const href=safeURL(url); return href ? `<a class="calendar-source-link" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : ""; }
function detailMarkup(date, store, sessions, accounts, accountId) {
  const plans=planRows(store,date), events=eventRows(store,date);
  return `<section class="calendar-detail panel"><div class="calendar-detail-head"><div><span class="eyebrow">当日详情</span><h2>${Number(date.slice(5,7))}月${Number(date.slice(8,10))}日 <small>${date.slice(0,4)}</small></h2></div><span class="calendar-date-pill">${fromISO(date).toLocaleDateString("zh-CN",{weekday:"long"})}</span></div>
    <div class="calendar-detail-section"><h3>市场交易时段</h3>${marketDaysMarkup(sessions,date)}</div>
    <div class="calendar-detail-section"><div class="calendar-section-title"><h3>市场与模拟盘表现</h3><span class="tag">收盘日线</span></div><div id="calendar-insights">${accountSelector(accounts,accountId)}<div class="calendar-benchmark-loading"><span class="spinner"></span>正在读取当日收盘行情…</div></div></div>
    <div class="calendar-detail-section"><div class="calendar-section-title"><h3>日程与订阅内容 <span class="muted">${plans.length+events.length}</span></h3><button type="button" class="text-link calendar-inline-button" data-action="calendar-focus-event">＋ 添加日程</button></div>${events.length||plans.length?`<ul class="calendar-plan-list">${[...events.map(x=>({kind:"event",...x})),...plans.map(x=>({kind:"plan",...x}))].sort((a,b)=>(a.time||"").localeCompare(b.time||"")).map(x=>`<li><span class="calendar-plan-time">${esc(x.time||"全天")}</span><div><strong>${esc(x.title||x.category)} ${x.kind==="event"?`<span class="tag">${esc(x.category)}</span>`:""}</strong><p>${esc(x.detail||x.text||"")}</p>${x.kind==="event"?sourceLink(x.sourceUrl):""}</div><button type="button" class="icon-button calendar-delete" data-action="${x.kind==="event"?"calendar-delete-event":"calendar-delete-plan"}" data-id="${esc(x.id)}" aria-label="删除日程">×</button></li>`).join("")}</ul>`:`<p class="field-help">这一天还没有计划或订阅事件。</p>`}
      <form id="calendar-plan-form" class="calendar-plan-form" novalidate><input type="hidden" name="date" value="${date}"><h3>记录日报 / 策略 / 操作日志</h3><div class="calendar-form-row"><select class="field" name="category" aria-label="计划类型">${CATEGORIES.map(x=>`<option>${x}</option>`).join("")}</select><input class="field calendar-time-input" name="time" type="time" aria-label="计划时间"><input class="field calendar-plan-text" name="text" aria-label="计划内容" placeholder="写下今天要做的事…" maxlength="240" required><button class="button primary small">保存</button></div><p class="form-error" id="calendar-plan-error" role="alert"></p></form>
      <form id="calendar-event-form" class="calendar-event-form" novalidate><input type="hidden" name="date" value="${date}"><h3>添加订阅事件 / 自定义日程</h3><div class="calendar-form-row"><select class="field" name="category" aria-label="订阅分类">${SUB_CATEGORIES.map(x=>`<option>${x}</option>`).join("")}</select><select class="field" name="subscriptionId" aria-label="关联订阅"><option value="">不关联订阅</option>${store.subscriptions.filter(x=>x.enabled).map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("")}</select><input class="field calendar-time-input" name="time" type="time" aria-label="事件时间"><input class="field calendar-plan-text" name="title" aria-label="事件标题" placeholder="简短标题" maxlength="80" required><button class="button small">添加</button></div><textarea class="field calendar-event-detail" name="detail" aria-label="事件详细说明" placeholder="详细说明（可粘贴公告摘要）" maxlength="600"></textarea><div class="calendar-event-meta"><input class="field" name="sourceUrl" type="url" aria-label="公告或原文来源链接" placeholder="公告 / 财报原文链接 https://…"><p class="form-error" id="calendar-event-error" role="alert"></p></div></form>
      <div class="calendar-ai-row"><span><strong>让 AI 帮你整理</strong><small>先生成草稿，确认后再加入这一天</small></span>${CATEGORIES.map(x=>`<button class="button small ghost" data-action="calendar-ai-draft" data-date="${date}" data-category="${x}">AI ${x}</button>`).join("")}</div>
    </div><div class="calendar-local-note">日程与订阅配置保存在当前浏览器；AI 内容需你主动点击确认后写入。</div></section>`;
}
function subscriptionMarkup(store) {
  return `<aside class="calendar-subscriptions panel"><div class="calendar-sub-head"><div><span class="eyebrow">订阅管理</span><h2>我的交易订阅</h2><p>开启后，订阅相关的日程标签会显示在对应日期；关闭后事件仍保留，重新开启即可恢复。</p></div><span class="tag accent">${store.subscriptions.filter(x=>x.enabled).length} 已开启</span></div><div class="calendar-sub-list">${store.subscriptions.length?store.subscriptions.map(x=>`<article class="calendar-sub-item"><div class="calendar-sub-main"><span class="calendar-sub-dot ${x.enabled?"enabled":""}"></span><div><strong>${esc(x.name)}</strong><small>${esc(x.category)} · ${x.enabled?"已订阅":"已暂停"}</small>${sourceLink(x.sourceUrl,"数据来源")}</div></div><div class="calendar-sub-actions"><button class="button small ${x.enabled?"":"primary"}" data-action="calendar-toggle-sub" data-id="${esc(x.id)}">${x.enabled?"暂停":"重新订阅"}</button><details class="calendar-edit-sub"><summary class="button small ghost">编辑</summary><form class="calendar-sub-edit-form" novalidate><input type="hidden" name="id" value="${esc(x.id)}"><input class="field" name="name" value="${esc(x.name)}" maxlength="60" required aria-label="订阅名称"><select class="field" name="category" aria-label="分类">${SUB_CATEGORIES.map(c=>`<option ${c===x.category?"selected":""}>${c}</option>`).join("")}</select><input class="field" name="sourceUrl" type="url" value="${esc(x.sourceUrl||"")}" placeholder="来源链接"><button class="button small primary">保存修改</button></form></details><button class="icon-button calendar-delete" data-action="calendar-delete-sub" data-id="${esc(x.id)}" aria-label="删除订阅">×</button></div></article>`).join(""):`<p class="field-help">还没有订阅。添加打新、逆回购、财报或你自己的日历源。</p>`}</div><form id="calendar-subscription-form" class="calendar-sub-create" novalidate><strong>添加订阅</strong><div class="calendar-form-row"><input class="field" name="name" aria-label="订阅名称" placeholder="例如：A股新股申购" maxlength="60" required><select class="field" name="category">${SUB_CATEGORIES.map(x=>`<option>${x}</option>`).join("")}</select><input class="field" name="sourceUrl" type="url" aria-label="公告源或信息源链接" placeholder="公告源 / 信息源链接"><button class="button primary small">创建订阅</button></div><p class="form-error" id="calendar-sub-error" role="alert"></p><p class="field-help">订阅配置目前由你管理；外部公告源暂不自动抓取，具体日期需手动添加事件。</p></form></aside>`;
}
export async function renderCalendarPage(route, accounts=[]) {
  const candidate=route.params.get("month")||isoLocal().slice(0,7), month=/^\d{4}-(0[1-9]|1[0-2])$/.test(candidate)?candidate:isoLocal().slice(0,7);
  const [year,mm]=month.split("-").map(Number), today=isoLocal(), fallback=month===today.slice(0,7)?today:`${month}-01`, rawDate=route.params.get("date")||fallback, selected=/^\d{4}-\d{2}-\d{2}$/.test(rawDate)&&rawDate.startsWith(month)?rawDate:fallback;
  const first=new Date(year,mm-1,1,12), start=new Date(year,mm-1,1-((first.getDay()+6)%7),12), end=new Date(start);end.setDate(start.getDate()+41);
  const store=readStore(), view=route.params.get("view")==="week"?"week":"month", collapsed=route.params.get("collapsed")==="1"; activeCollapsed=collapsed; let sessions={days:[]};
  try { sessions=await request(`/markets/calendar?start=${isoLocal(start)}&end=${isoLocal(end)}&markets=CN,HK,US`,{timeout:12000}); } catch(error) { sessions={days:[],error:error.message}; }
  const prev=new Date(year,mm-2,1,12), next=new Date(year,mm,1,12), accountId=route.params.get("account")||accounts[0]?.account_id||""; activeAccount=accountId;
  const prevMonth=isoLocal(prev).slice(0,7), nextMonth=isoLocal(next).slice(0,7);
  return `<div class="content-page calendar-page"><div class="page-heading"><div><div class="eyebrow">交易日 · 计划 · 订阅</div><h1>交易日历</h1><p>一处安排 A 股、港股、美股交易时段、模拟盘复盘与订阅提醒。</p></div><div class="actions"><button class="button" data-action="calendar-enable-reminders">${store.reminders?"桌面提醒已开启":"开启桌面提醒"}</button></div></div>
    <div class="calendar-market-strip"><div class="calendar-strip-title"><span class="calendar-live-indicator"></span><strong>常规交易时段</strong><small>休市日以交易所日历为准</small></div><div class="calendar-hours"><div><b>A股</b><span>09:30–11:30</span><span>13:00–15:00</span><small>北京时间</small></div><div><b>美股</b><span>09:30–16:00</span><small>${usOpenBeijingTime()}</small></div><div><b>港股</b><span>09:30–12:00</span><span>13:00–16:00</span><small>香港时间</small></div></div></div>
    ${sessions.error?`<div class="alert">交易所日历暂不可用：${esc(sessions.error)}。日期网格仍可用于记录。</div>`:""}<div class="calendar-layout">${subscriptionMarkup(store)}<div class="calendar-main"><section class="calendar-month panel"><header class="calendar-month-head"><div><span class="eyebrow">日历视图</span><h2>${year}年 ${String(mm).padStart(2,"0")}月</h2></div><div class="calendar-month-actions"><a class="icon-button" href="${calendarURL(prevMonth,`${prevMonth}-01`,view)}" aria-label="上个月">‹</a><a class="button small ghost" href="${calendarURL(today.slice(0,7),today,view)}">今天</a><a class="icon-button" href="${calendarURL(nextMonth,`${nextMonth}-01`,view)}" aria-label="下个月">›</a><div class="calendar-view-switch"><a class="${view==="month"?"active":""}" href="${calendarURL(month,selected,"month")}">月</a><a class="${view==="week"?"active":""}" href="${calendarURL(month,selected,"week")}">周</a></div><button class="button small ghost calendar-collapse-button" type="button" data-action="calendar-toggle-collapse" aria-expanded="${!collapsed}">${collapsed?"展开日历":"收起日历"}</button></div></header>${collapsed?compactWeekMarkup(selected,store,sessions):`<div class="calendar-legend"><span><i class="legend-open"></i>交易日</span><span><i class="legend-ipo"></i>订阅事件</span><span><i class="legend-plan"></i>计划</span><span class="legend-pnl">月格内显示模拟盘日盈亏</span></div>${view==="week"?weekGridMarkup(selected,store,sessions):monthGridMarkup(month,selected,store,sessions,{})}`}</section>${detailMarkup(selected,store,sessions,accounts,accountId)}</div></div><p class="calendar-footnote">交易时段由 XSHG、XHKG、XNYS 交易所日历计算；指数、个股和模拟盘只显示已接入的历史收盘日线。通知仅在工作台打开时检查。</p></div>`;
}
export async function mountCalendar(date,accountId,view="month") { loadInsights(date,accountId); if(activeCollapsed)loadWeekPnl(date,accountId);else loadMonthPnl(date.slice(0,7),accountId); checkReminder(); }
let reminderTimer;
export function cleanupCalendar(){clearInterval(reminderTimer);reminderTimer=null;}
async function loadMonthPnl(month,accountId) {
  if(!accountId)return; const [y,m]=month.split("-").map(Number), start=new Date(y,m-1,1,12), end=new Date(y,m,0,12);
  try { const data=await request(`/paper/performance/history?account_id=${encodeURIComponent(accountId)}&start=${isoLocal(start)}&end=${isoLocal(end)}`,{timeout:15000}); const map=Object.fromEntries((data.days||[]).map(x=>[x.date,x]));
    document.querySelectorAll("[data-pnl-date]").forEach(el=>{const x=map[el.dataset.pnlDate];if(!x?.complete)return;el.textContent=`${x.day_pnl>0?"+":""}${money(x.day_pnl,x.currency)}`;el.classList.add(tone(x.day_pnl));});
  } catch {}
}
async function loadWeekPnl(date,accountId) {
  if(!accountId)return;const selected=fromISO(date),start=new Date(selected);start.setDate(selected.getDate()-((selected.getDay()+6)%7));const end=new Date(start);end.setDate(start.getDate()+6);
  try{const data=await request(`/paper/performance/history?account_id=${encodeURIComponent(accountId)}&start=${isoLocal(start)}&end=${isoLocal(end)}`,{timeout:12000}),map=Object.fromEntries((data.days||[]).map(x=>[x.date,x]));document.querySelectorAll("[data-pnl-date]").forEach(el=>{const x=map[el.dataset.pnlDate];if(!x?.complete)return;el.textContent=`${x.day_pnl>0?"+":""}${money(x.day_pnl,x.currency)}`;el.classList.add(tone(x.day_pnl));});}catch{}
}
async function loadInsights(date,accountId) {
  const target=document.querySelector("#calendar-insights");if(!target)return;
  const selector=target.querySelector("#calendar-account")?.outerHTML||"";
  const [insights,account]=await Promise.all([request(`/calendar/insights?date=${date}`,{timeout:10000}).catch(()=>null),accountId?request(`/paper/performance?account_id=${encodeURIComponent(accountId)}&date=${date}`,{timeout:10000}).catch(()=>null):Promise.resolve(null)]);
  if(!document.contains(target))return;
  const marketGroups=[{name:"A股指数",ids:["INDEX:SH000001","INDEX:SZ399001","INDEX:SH000300","INDEX:SZ399006"]},{name:"港股指数",ids:["INDEX:HSI"]},{name:"美股指数",ids:["INDEX:SPX","INDEX:NASDAQ","INDEX:DJIA"]}];
  const indexes=insights?.indices||[]; const groupMarkup=marketGroups.map(g=>{const rows=indexes.filter(x=>g.ids.includes(x.id));if(!rows.length)return "";return `<div class="calendar-insight-group"><h4>${g.name}</h4><div class="calendar-insight-grid">${rows.map(x=>`<div class="calendar-benchmark"><span>${esc(x.name)}</span>${x.change_percent==null?`<strong class="calendar-no-data">暂无历史日线</strong>`:`<strong class="mono ${tone(x.change_percent)}">${percent(x.change_percent)}</strong>`}<small>${x.close!=null?`收盘 ${Number(x.close).toLocaleString("zh-CN",{maximumFractionDigits:2})} · `:""}${esc(x.source||"需先采集历史行情")}</small></div>`).join("")}</div></div>`}).join("");
  const watch=(insights?.watchlist||[]).filter(x=>x.market==="CN"||x.market==="US"||x.market==="HK");
  const watchMarkup=`<div class="calendar-insight-group"><h4>自选股涨跌 <small>最多展示 12 只</small></h4>${watch.length?`<div class="calendar-watch-list">${watch.map(x=>`<div><span><strong>${esc(x.name)}</strong><small>${esc(x.instrument_id)}</small></span>${x.change_percent==null?`<b class="calendar-no-data">暂无</b>`:`<b class="mono ${tone(x.change_percent)}">${percent(x.change_percent)}</b>`}</div>`).join("")}</div>`:`<p class="field-help">自选列表为空或当天没有已保存的收盘日线。</p>`}</div>`;
  const flow=insights?.market_flow, flowText=flow?.row?JSON.stringify(flow.row):"暂无已缓存的市场资金流记录";
  const connect=insights?.connect_flow?.note||"未接入";
  const accountMarkup=accountId?`<div class="calendar-account-pnl"><span>模拟盘日盈亏</span>${account?.complete?`<strong class="mono ${tone(account.day_pnl)}">${account.day_pnl>0?"+":""}${money(account.day_pnl,account.currency)} <small>(${percent(account.day_change_percent)})</small></strong><small>估值 ${money(account.equity,account.currency)} · ${date}</small>`:`<strong class="calendar-no-data">${account?.reason==="future_date"?"尚未发生":account?.reason==="before_account"?"账户尚未创建":account?.is_session===false?"非交易日":"日线不完整"}</strong><small>${account?.missing_bars?.length?`缺少 ${account.missing_bars.map(esc).join("、")} 日线`:"需要成交账本和持仓的连续收盘价"}</small>`}</div>`:"";
  const flowEntries=flow?.row?Object.entries(flow.row).filter(([key])=>!/(日期|date)/i.test(key)).slice(0,5):[];
  target.innerHTML=`${selector}${accountMarkup}<div class="calendar-insight-group"><h4>主要市场指数</h4>${groupMarkup||`<p class="field-help">尚无指数历史数据。</p>`}</div>${watchMarkup}<div class="calendar-flow-note"><strong>A股市场资金流</strong>${flowEntries.length?`<div class="calendar-flow-values">${flowEntries.map(([key,value])=>`<span>${esc(key)}<b>${esc(value??"—")}</b></span>`).join("")}</div>`:`<p>暂无已缓存的市场资金流记录</p>`}<small>通用市场资金流不等于北向 / 南向资金。${esc(connect)}</small></div><p class="field-help">日涨跌按所选日与上一条收盘日线计算；缺少历史数据时不会用当前行情倒填。</p>`;
}
function checkReminder() {
  clearInterval(reminderTimer); reminderTimer=setInterval(()=>{const store=readStore();if(!store.reminders||!("Notification" in window)||Notification.permission!=="granted")return;const now=new Date(),date=isoLocal(now),minute=`${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`;const items=[...store.plans.map(x=>({...x,title:x.category,note:x.text})),...eventRows(store,date)].filter(x=>x.date===date&&x.time===minute&&!x.notified);for(const x of items){new Notification(x.title||x.category,{body:x.note||x.detail||"打开交易日历查看安排"});x.notified=true;}if(items.length){store.plans=store.plans.map(x=>items.find(i=>i.id===x.id)||x);store.events=store.events.map(x=>items.find(i=>i.id===x.id)||x);writeStore(store);}},30000);
}
function rerender(date,view="month"){location.hash=calendarURL(date.slice(0,7),date,view);}
export function handleCalendarAction(button) {
  const action=button.dataset.action;if(!action?.startsWith("calendar-"))return false;
  const store=readStore(), id=button.dataset.id;
  if(action==="calendar-toggle-collapse"){const params=new URLSearchParams(location.hash.split("?")[1]||"");if(params.get("collapsed")==="1")params.delete("collapsed");else params.set("collapsed","1");location.hash="/calendar?"+params.toString();return true;}
  if(action==="calendar-enable-reminders") { const enable=async()=>{if(!("Notification" in window)){notify("当前浏览器不支持桌面通知","error");return;}const permission=await Notification.requestPermission();if(permission!=="granted"){notify("未获得桌面通知权限","error");return;}store.reminders=true;writeStore(store);notify("桌面提醒已开启");renderCalendarCurrent();};enable();return true; }
  if(action==="calendar-delete-plan"||action==="calendar-delete-event"){if(action.endsWith("plan"))store.plans=store.plans.filter(x=>x.id!==id);else store.events=store.events.filter(x=>x.id!==id);if(writeStore(store)){notify("日程已删除");renderCalendarCurrent();}return true;}
  if(action==="calendar-toggle-sub"){store.subscriptions=store.subscriptions.map(x=>x.id===id?{...x,enabled:!x.enabled}:x);if(writeStore(store)){notify("订阅状态已更新");renderCalendarCurrent();}return true;}
  if(action==="calendar-delete-sub"){store.subscriptions=store.subscriptions.filter(x=>x.id!==id);store.events=store.events.map(x=>x.subscriptionId===id?{...x,subscriptionId:""}:x);if(writeStore(store)){notify("订阅已删除，原日程保留为自定义事件");renderCalendarCurrent();}return true;}
  if(action==="calendar-add-hour"){const date=button.dataset.date,time=button.dataset.time;location.hash=calendarURL(date.slice(0,7),date,"week");setTimeout(()=>{const field=document.querySelector('#calendar-plan-form input[name="time"]');const form=document.querySelector("#calendar-plan-form");if(field)field.value=time;form?.querySelector('[name="text"]')?.focus();},500);return true;}
  if(action==="calendar-focus-event"){document.querySelector("#calendar-event-form")?.scrollIntoView({behavior:"smooth",block:"center"});document.querySelector('#calendar-event-form [name="title"]')?.focus();return true;}
  if(action==="calendar-ai-draft"){const date=button.dataset.date,category=button.dataset.category;window.dispatchEvent(new CustomEvent("calendar-ai-draft",{detail:{date,category}}));return true;}
  if(action==="calendar-add-ai")return false;
  return true;
}
function renderCalendarCurrent(){window.dispatchEvent(new Event("calendar-refresh"));}
export function addAICalendarPlan(date,category,text){const store=readStore(),content=(text||"").trim();if(!content)return false;store.plans.push({id:crypto.randomUUID(),date,category,text:content.slice(0,1200),createdAt:new Date().toISOString()});if(!writeStore(store))return false;notify("AI 草稿已加入交易日历");renderCalendarCurrent();return true;}
export function handleCalendarSubmit(form,values){
  const store=readStore();
  if(form.id==="calendar-plan-form"){const text=(values.text||"").trim();if(!text){const input=form.querySelector('[name="text"]'),error=form.querySelector(".form-error");error.textContent="请填写计划内容。";input.setAttribute("aria-invalid","true");input.focus();return true;}store.plans.push({id:crypto.randomUUID(),date:values.date,time:values.time,category:values.category,text,createdAt:new Date().toISOString()});if(writeStore(store)){notify("计划已保存到日历");renderCalendarCurrent();}return true;}
  if(form.id==="calendar-event-form"){const title=(values.title||"").trim();if(!title){form.querySelector(".form-error").textContent="请填写事件标题。";form.querySelector('[name="title"]').focus();return true;}const source=safeURL(values.sourceUrl||"");if(values.sourceUrl&&!source){form.querySelector(".form-error").textContent="来源链接需要使用 http 或 https。";form.querySelector('[name="sourceUrl"]').focus();return true;}store.events.push({id:crypto.randomUUID(),date:values.date,time:values.time,title,category:values.category,subscriptionId:values.subscriptionId||"",detail:(values.detail||"").trim(),sourceUrl:source,notified:false});if(writeStore(store)){notify("日历事件已添加");renderCalendarCurrent();}return true;}
  if(form.id==="calendar-subscription-form"){const name=(values.name||"").trim();if(!name){form.querySelector(".form-error").textContent="请填写订阅名称。";form.querySelector('[name="name"]').focus();return true;}const source=safeURL(values.sourceUrl||"");if(values.sourceUrl&&!source){form.querySelector(".form-error").textContent="信息源链接需要使用 http 或 https。";return true;}store.subscriptions.push({id:crypto.randomUUID(),name,category:values.category,sourceUrl:source,enabled:true});if(writeStore(store)){notify("订阅已创建");renderCalendarCurrent();}return true;}
  if(form.classList.contains("calendar-sub-edit-form")){const id=values.id,name=(values.name||"").trim(),source=safeURL(values.sourceUrl||"");if(!name){form.querySelector('[name="name"]').focus();return true;}if(values.sourceUrl&&!source){notify("信息源链接需要使用 http 或 https。","error");return true;}store.subscriptions=store.subscriptions.map(x=>x.id===id?{...x,name,category:values.category,sourceUrl:source}:x);store.events=store.events.map(x=>x.subscriptionId===id?{...x,category:values.category}:x);if(writeStore(store)){notify("订阅信息已更新");renderCalendarCurrent();}return true;}
  return false;
}
