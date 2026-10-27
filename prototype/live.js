import { request } from "./api.js";
import { ensureRecentIdentity } from "./identity.js";
import {
  esc,
  money,
  number,
  time,
  icon,
  empty,
  confirmDialog,
  notify,
} from "./ui.js";
let status = null,
  sendKey = null;
const labels = {
  validating: "校验中，尚未发送",
  dispatching: "发送中",
  submitted: "券商已接收，待查询",
  unknown: "提交结果未知，禁止重发",
  rejected: "未发送 / 券商拒绝",
  broker_reported: "已有券商回报",
  cancel_requested: "撤单已请求",
  cancel_unknown: "撤单结果待核对",
  partially_filled: "部分成交",
  filled: "全部成交",
  canceled: "已撤销",
};
function rows(orders) {
  return orders.length
    ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>委托</th><th>方向 / 数量</th><th>金额 / 限价</th><th>券商状态</th><th>操作</th></tr></thead><tbody>${orders
        .map((o) => {
          const b = JSON.parse(o.body_json);
          return `<tr><td>${esc(b.instrument_id)}<small>${esc(o.connection_id)}</small><small>${esc(o.order_id)}</small></td><td>${b.side === "buy" ? "买入" : "卖出"} ${number(b.quantity, 0)}</td><td>${number(o.notional)}<small>限价 ${esc(b.limit_price)}</small></td><td><span class="tag ${o.status === "unknown" ? "amber" : ""}">${labels[o.status] || esc(o.status)}</span><small>${esc(o.broker_status || "尚无券商回报")}</small>${o.error ? `<small class="negative">${esc(o.error)}</small>` : ""}<small>请求流水 ${esc(o.client_serial)}</small><small>${time(o.updated_at)}</small></td><td>${o.broker_order_id && !["filled", "canceled", "rejected", "cancel_requested", "cancel_unknown"].includes(o.status) ? `<button class="button small danger" data-action="live-cancel" data-id="${esc(o.order_id)}">请求撤单</button>` : "—"}</td></tr>`;
        })
        .join("")}</tbody></table></div>`
    : empty(
        "暂无真实委托",
        "这里仅展示本平台的真实券商委托；不会混入模拟订单。",
      );
}
export async function renderLive(r, signal, ui) {
  const [s, orders] = await Promise.all([
    request("/live/status", { signal }),
    request("/live/orders", { signal }),
  ]);
  if (signal.aborted) return;
  status = s;
  ui.setPage(
    ui.page(
      ui.heading(
        "实盘交易",
        "富途 OpenD 真实账户。每笔限价委托需本人预览和确认。",
        `<span class="tag amber">真实资金 · 与模拟盘独立</span>`,
      ) +
        `<div class="alert"><strong>实盘接入状态</strong><p>${esc(s.note)}</p><p>在富途 OpenD 登录并手动解锁交易。网页不接收富途登录密码或交易密码；AI 不会自主发送真实订单。发送开关默认关闭。</p></div><div class="paper-account-grid section-gap">${s.catalog.map((c) => ui.panel(c.name, `<div class="panel-body"><span class="tag">${esc(c.market)}</span><p class="section-gap">${esc(c.interface)}</p><p class="field-help section-gap">${esc(c.status)}</p></div>`)).join("")}</div>` +
        `<div class="paper-account-grid section-gap">${s.connections.length ? s.connections.map((c) => ui.panel(c.label, `<div class="panel-body"><span class="tag ${c.trading_enabled ? "amber" : ""}">${c.trading_enabled ? "已配置发送 · 解锁待确认" : "只读 / 发送关闭"}</span><p class="field-help section-gap">${esc(c.market)} · ${esc(c.currency)} · 账户尾号 ${esc(c.account_suffix)}</p><p class="field-help">单笔上限 ${esc(c.max_order_notional)} · 当日上限 ${esc(c.max_daily_notional)}</p></div>`)).join("") : empty("尚无富途真实账户", "请在 OpenD 登录，并在服务端配置真实账户白名单。")}</div>` +
        `<div class="split section-gap">${ui.panel("实盘限价委托", `<form id="live-order-form" class="panel-body" novalidate data-draft><div class="form-row"><label class="field-label" for="live-connection">已配置券商连接</label><select id="live-connection" class="field" name="connection_id">${s.connections.length ? s.connections.map((c) => `<option value="${esc(c.id)}" ${c.configured ? "" : "disabled"}>${esc(c.label)} · ${esc(c.market)} · ${c.trading_enabled ? "已配置发送开关" : "只读 / 发送关闭"}</option>`).join("") : '<option value="">尚未配置券商API</option>'}</select></div><div id="live-connection-note" class="field-help"></div><div class="form-row section-gap"><label class="field-label" for="live-instrument">股票代码</label><input id="live-instrument" class="field" name="instrument_id" placeholder="HK:00700 / US:AAPL" /></div><div class="form-grid"><div class="form-row"><label class="field-label" for="live-side">方向</label><select class="field" id="live-side" name="side"><option value="buy">买入</option><option value="sell">卖出</option></select></div><div class="form-row"><label class="field-label" for="live-quantity">股数</label><input id="live-quantity" class="field" type="number" min="1" step="1" name="quantity" /></div><div class="form-row"><label class="field-label" for="live-price">委托限价（账户原币种）</label><input id="live-price" class="field" type="number" min="0.0001" step="0.0001" name="limit_price" /></div></div><p class="field-help">仅现金限价委托，按券商返回的现金可买/可卖数量校验，另保留1%费用缓冲。提交不代表成交，费用与成交以券商回报为准。</p><div class="form-error" id="live-error" role="alert"></div><div class="actions"><button class="button primary" type="submit" ${s.connections.some((c) => c.configured) ? "" : "disabled"}>预览真实委托</button><button class="button" type="button" data-action="live-account" ${s.connections.some((c) => c.configured) ? "" : "disabled"}>查询真实账户</button></div></form>`)}${ui.panel("真实账户与持仓", `<div id="live-account-view" class="panel-body">${empty("尚未查询真实账户", "配置完成后，由你点击查询；系统不会用模拟余额替代。")}</div>`)}</div>` +
        `<section class="panel section-gap"><div class="panel-header"><div><h2>本平台最近100笔实盘委托</h2><p>超时或断线先核对券商，结果未知时停止后续发送。</p></div><button class="button small" data-action="live-reconcile" ${s.connections.some((c) => c.configured) ? "" : "disabled"}>${icon("refresh")}核对所选连接</button></div><div id="live-orders">${rows(orders)}</div><p class="field-help panel-body" id="live-feedback" role="status"></p></section>`,
    ),
  );
  const update = () => {
    const c = s.connections.find(
      (c) => c.id === document.querySelector("#live-connection").value,
    );
    document.querySelector("#live-connection-note").textContent = c
      ? `单笔上限 ${c.max_order_notional}；当日委托总额 ${c.max_daily_notional}；白名单 ${c.symbols.join("、") || "未设置，不能发送"}。${c.error || "配置存在，仍需查询验证连通性。"}`
      : "先在服务端配置券商授权接口，详见仓库 docs/BROKER_SETUP.md。";
  };
  document.querySelector("#live-connection").onchange = update;
  update();
}
export async function handleLiveSubmit(form, values, ui) {
  if (form.id !== "live-order-form") return false;
  await ui.busy(form, async () => {
    try {
      if (
        !values.connection_id ||
        !values.instrument_id ||
        !Number.isInteger(Number(values.quantity)) ||
        !(Number(values.quantity) > 0) ||
        !(Number(values.limit_price) > 0)
      )
        throw new Error("请选择券商并填写股票、整数股数和限价");
      if (!(await ensureRecentIdentity())) return;
      const body = {
        connection_id: values.connection_id,
        instrument_id: values.instrument_id.trim().toUpperCase(),
        side: values.side,
        quantity: Number(values.quantity),
        limit_price: values.limit_price,
      };
      // Reuse an unexpired preview after an uncertain client response; never create a fresh order on retry.
      const signature = JSON.stringify(body);
      if (!sendKey || sendKey.signature !== signature)
        sendKey = { signature, key: crypto.randomUUID(), preview: null };
      const d =
        sendKey.preview ||
        (await request("/live/orders/preview", {
          method: "POST",
          body,
          timeout: 45000,
        }));
      sendKey.preview = d;
      if (!d.trading_enabled)
        throw new Error(
          "预览已完成，但实盘发送未启用；请先完成券商联调和本人配置。",
        );
      const yes = await confirmDialog(
        "确认发送真实券商委托",
        `<div class="alert error"><strong>这笔订单使用真实资金</strong></div><dl><dt>连接</dt><dd>${esc(d.connection_id)}</dd><dt>账户核对</dt><dd>${d.account_suffix ? "尾号 ****" + esc(d.account_suffix) : "请先查询并核对富途真实账户"}</dd><dt>股票 / 方向</dt><dd>${esc(d.instrument_id)} / ${d.side === "buy" ? "买入" : "卖出"}</dd><dt>股数</dt><dd>${number(d.quantity, 0)}</dd><dt>限价</dt><dd>${money(d.limit_price, d.currency)}</dd><dt>委托名义金额</dt><dd>${money(d.notional, d.currency)}</dd><dt>有效期</dt><dd>至 ${time(new Date(d.expires_at * 1000).toISOString())}</dd></dl><p>确认后发送给券商，可能立即成交。费用、成交与撤单结果以券商回报为准。</p>`,
        "确认发送真实订单",
        true,
      );
      if (!yes) {
        sendKey = null;
        return;
      }
      const result = await request("/live/orders", {
        method: "POST",
        body: { preview_id: d.preview_id, confirm: "REAL ORDER" },
        headers: { "Idempotency-Key": sendKey.key },
        timeout: 60000,
      });
      sendKey = null;
      notify(`${result.order_id} · ${labels[result.status] || result.status}`);
      ui.renderRoute();
    } catch (e) {
      if (e.status && [403, 404, 409, 422].includes(e.status)) sendKey = null;
      ui.formError("live-error", e.message);
      notify(e.message);
    }
  });
  return true;
}
export async function handleLiveAction(button, ui) {
  const action = button.dataset.action;
  if (!action?.startsWith("live-")) return false;
  button.disabled = true;
  try {
    const identifier = document.querySelector("#live-connection")?.value;
    if (action !== "live-cancel" && !identifier)
      throw new Error("请先选择已配置的券商连接");
    if (action === "live-account") {
      const a = await request(
        "/live/accounts/" + encodeURIComponent(identifier),
        { timeout: 45000 },
      );
      document.querySelector("#live-account-view").innerHTML =
        `<h3>${esc(identifier)} · ${esc(a.currency)}${a.account_suffix ? " · 尾号 ****" + esc(a.account_suffix) : " · 富途账户"}</h3><p class="paper-balance section-gap">${money(a.cash, a.currency)}</p><p class="field-help">券商返回的可用现金 · 查询时间 ${typeof a.as_of === "number" ? time(new Date(a.as_of * 1000).toISOString()) : time(a.as_of)}</p>${a.positions.length ? `<div class="table-scroll section-gap"><table class="data-table"><thead><tr><th>股票</th><th>数量 / 可卖</th><th>成本</th></tr></thead><tbody>${a.positions.map((p) => `<tr><td>${esc(p.instrument_id)}</td><td>${number(p.quantity)} / ${number(p.sellable)}</td><td>${number(p.average_cost, 4)}</td></tr>`).join("")}</tbody></table></div>` : empty("暂无持仓", "以券商当前返回为准。")}`;
    } else if (action === "live-reconcile") {
      const result = await request(
        "/live/connections/" + encodeURIComponent(identifier) + "/reconcile",
        { method: "POST", timeout: 45000 },
      );
      document.querySelector("#live-orders").innerHTML = rows(await request("/live/orders"));
      document.querySelector("#live-feedback").textContent = result.note;
      notify("已读取券商委托回报");
    } else if (action === "live-cancel") {
      if (!(await ensureRecentIdentity())) return true;
      if (
        !(await confirmDialog(
          "请求撤销真实委托",
          "<p>将向券商请求撤销这笔真实委托。已经成交的部分不能撤销，撤单请求不代表撤单成功。</p>",
          "向券商请求撤单",
          true,
        ))
      )
        return true;
      const result = await request(
        "/live/orders/" + encodeURIComponent(button.dataset.id) + "/cancel",
        { method: "POST", timeout: 45000 },
      );
      notify(labels[result.status] || result.status);
      ui.renderRoute();
    }
  } catch (e) {
    notify(e.message);
    const feedback = document.querySelector("#live-feedback");
    if (feedback) feedback.textContent = e.message;
  } finally {
    button.disabled = false;
  }
  return true;
}
