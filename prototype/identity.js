import { request, configureSecurity } from "./api.js";
import { esc, icon, showDialog, notify, time, empty } from "./ui.js";
let identity = null,
  lastActivity = Date.now(),
  pendingReady = null,
  reauthPending = null,
  readyPromise = null;
let composing = false;
let authView = 0;
document.addEventListener("compositionstart", () => {
  composing = true;
});
document.addEventListener("compositionend", () => {
  composing = false;
});
const root = () => document.querySelector("#identity-root");
const workspace = () => document.querySelector(".workspace");
export const getIdentity = () => identity;
for (const event of ["pointerdown", "keydown", "touchstart"])
  document.addEventListener(
    event,
    () => {
      lastActivity = Date.now();
    },
    { passive: true },
  );
function field(id, label, type = "text", autocomplete = "off") {
  return `<div class="form-row"><label class="field-label" for="${id}">${label}</label><div class="secret-field"><input class="field" id="${id}" name="${id}" type="${type}" autocomplete="${autocomplete}" ${type === "password" ? 'maxlength="256"' : ""} />${type === "password" ? `<button class="icon-button reveal-secret" type="button" data-reveal="${id}" aria-label="显示${label}">${icon("eye")}</button>` : ""}</div></div>`;
}
function frame(title, subtitle, body) {
  return `<main class="identity-shell"><section class="identity-intro"><a class="brand" href="#/chat"><div class="brand-mark">${icon("spark")}</div>Finch <span>PRIVATE RESEARCH</span></a><div><p class="eyebrow">你的私人投研空间</p><h1>研究市场，<br>掌握自己的判断。</h1><p>行情、公司资料与策略研究，<br>只向你的账户开放。</p></div><p class="identity-security">密码登录 · 私人数据访问控制</p></section><section class="identity-form"><p class="eyebrow">FINCH / IDENTITY</p><h2>${esc(title)}</h2><p class="field-help">${esc(subtitle)}</p>${body}<p class="identity-note">资金账户与 Agent 配置保存在服务端。公共注册已关闭。</p></section></main>`;
}
function showRoot() {
  authView += 1;
  document.title = "身份验证 — Finch";
  workspace().hidden = true;
  root().hidden = false;
  document.querySelectorAll("dialog[open]").forEach((d) => d.close());
}
function revealButtons(scope = document) {
  scope.querySelectorAll("[data-reveal]").forEach(
    (button) =>
      (button.onclick = () => {
        const input = document.getElementById(button.dataset.reveal);
        const visible = input.type === "password";
        input.type = visible ? "text" : "password";
        button.setAttribute(
          "aria-label",
          visible ? "隐藏敏感内容" : "显示敏感内容",
        );
      }),
  );
}
async function submit(form, handler) {
  if (form.dataset.busy) return;
  form.dataset.busy = "true";
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  const error = form.querySelector("[role=alert]");
  error.textContent = "";
  try {
    await handler(Object.fromEntries(new FormData(form)));
  } catch (e) {
    for (const input of form.querySelectorAll(
      'input[type="password"],input[autocomplete="one-time-code"]',
    ))
      input.value = "";
    error.textContent = e.message;
    const invalid = form.querySelector("input");
    invalid?.setAttribute("aria-invalid", "true");
    invalid?.setAttribute("aria-describedby", error.id);
    invalid?.focus();
  } finally {
    delete form.dataset.busy;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}
function ready() {
  root().innerHTML = "";
  root().hidden = true;
  workspace().hidden = false;
  pendingReady?.();
  pendingReady = null;
  document.dispatchEvent(new CustomEvent("finch:authenticated"));
}
function loginForm(message = "", username = "") {
  showRoot();
  const view = authView;
  root().innerHTML = frame(
    "登录私人空间",
    "输入账户和密码即可登录。",
    `${message ? `<div class="alert">${esc(message)}</div>` : ""}<form id="login-form" novalidate>${field("username", "账号", "text", "username")}${field("password", "密码", "password", "current-password")}<div class="form-error" id="login-error" role="alert"></div><button class="button primary" type="submit">登录</button></form><details class="section-gap"><summary>无法登录或尚未创建账户</summary><p class="field-help">账户由本人在本机终端创建，系统未开放公共注册。</p><code>.venv/bin/python -m app.manage init-owner</code><p class="field-help">忘记密码可在项目终端运行 .venv/bin/python -m app.manage reset-password。</p></details>`,
  );
  revealButtons(root());
  const form = document.querySelector("#login-form");
  form.querySelector("#username").value = username;
  form.onsubmit = (e) => {
    e.preventDefault();
    if (composing || e.isComposing) return;
    submit(form, async (values) => {
      if (!values.username.trim() || !values.password)
        throw Error("请输入账号和密码");
      const result = await request("/auth/login", {
        method: "POST",
        body: values,
      });
      form.querySelector("#password").value = "";
      if (view !== authView) return;
      identity = result;
      ready();
    });
  };
  form.querySelector("#username").focus();
}
export async function signOut() {
  let message = "已退出；当前浏览器中的私人数据已隐藏。";
  try {
    await request("/auth/logout", { method: "POST", body: {} });
  } catch {
    message =
      "当前页面已锁定，但未能确认服务端撤销。网络恢复后请重新登录并检查会话。";
  }
  identity = null;
  document.dispatchEvent(new CustomEvent("finch:signed-out"));
  loginForm(message);
}

export async function ensureRecentIdentity() {
  if (identity?.reauthenticated_until > Date.now() / 1000 + 30) return true;
  return ensureFresh();
}
async function ensureFresh() {
  if (reauthPending) return reauthPending;
  reauthPending = new Promise((resolve) => {
    const dialog = showDialog(
      "重新验证身份",
      `<p>这项操作涉及账户数据、模拟订单或资料删除。请确认当前账户密码。</p><form id="reauth-form" novalidate>${field("reauth-password", "密码", "password", "current-password")}<div class="form-error" id="reauth-error" role="alert"></div><button class="button primary" type="submit">验证并继续</button></form>`,
    );
    let verified = false;
    const form = document.querySelector("#reauth-form");
    revealButtons(form);
    form.onsubmit = (e) => {
      e.preventDefault();
      if (composing) return;
      submit(form, async (values) => {
        const verifiedIdentity = await request("/auth/reauth", {
          method: "POST",
          body: {
            password: values["reauth-password"],
          },
        });
        identity = verifiedIdentity.identity;
        verified = true;
        form.reset();
        dialog.close();
      });
    };
    dialog.addEventListener(
      "close",
      () => {
        form.reset();
        resolve(verified);
      },
      { once: true },
    );
  }).finally(() => {
    reauthPending = null;
  });
  return reauthPending;
}
configureSecurity({
  csrf: () => identity?.csrf_token,
  active: () => Date.now() - lastActivity < 60000,
  reauthenticate: ensureFresh,
  expired: () => {
    if (!identity) return;
    identity = null;
    document.dispatchEvent(new CustomEvent("finch:locked"));
    loginForm("会话已结束，请重新登录。当前未发送草稿保留在本页内存中。");
  },
});
export async function requireIdentity() {
  showRoot();
  root().innerHTML = frame("正在确认身份", "正在读取本机账户状态…", "");
  const status = await request("/auth/status");
  if (!status.initialized) {
    root().innerHTML = frame(
      "初始化私人空间",
      "先在本机终端创建唯一的拥有者账户，再回来登录。",
      `<div class="alert">创建密码需在本机终端输入，不写入 ENV 或仓库。</div><pre class="code-data section-gap">python -m app.manage init-owner</pre><p class="field-help">密码至少14个字符；创建后即可用账号密码登录。</p><button class="button primary section-gap" id="check-owner">我已创建账户，继续登录</button>`,
    );
    document.querySelector("#check-owner").onclick = () =>
      requireIdentity().catch((error) => notify(error.message));
  } else {
    try {
      identity = await request("/auth/me");
      if (identity.setup_required) throw Error("请重新使用密码登录");
      else {
        ready();
        return;
      }
    } catch {
      identity = null;
      loginForm();
    }
  }
  if (!readyPromise)
    readyPromise = new Promise((resolve) => {
      pendingReady = resolve;
    });
  return readyPromise;
}
export async function renderSecurityPage() {
  const [me, sessions, audit] = await Promise.all([
    request("/auth/me"),
    request("/auth/sessions"),
    request("/auth/audit"),
  ]);
  return `<div class="content-page"><div class="page-heading"><div><h1>账户安全</h1><p>管理私人空间的身份、会话和访问记录。</p></div><button class="button" id="security-logout">退出登录</button></div><div class="stat-grid"><div class="stat"><div class="stat-label">当前账户</div><div class="stat-value">${esc(me.user.username)}</div><div class="stat-note">唯一拥有者</div></div><div class="stat"><div class="stat-label">登录方式</div><div class="stat-value">账号密码</div><div class="stat-note">交易确认仅重验账户密码</div></div><div class="stat"><div class="stat-label">会话最长有效期</div><div class="stat-value">8 小时</div><div class="stat-note">闲置 ${Math.floor(me.idle_seconds / 60)} 分钟退出</div></div><div class="stat"><div class="stat-label">公开注册</div><div class="stat-value">已关闭</div><div class="stat-note">账户由本机终端管理</div></div></div><div class="split section-gap"><section class="panel"><div class="panel-header"><h2>登录设备与会话</h2></div><div class="panel-body">${sessions.map((s) => `<article class="provider-item section-gap"><div><strong>${s.current ? "当前会话" : "其他会话"}</strong><button class="button small" data-revoke-session="${s.current ? "current" : esc(s.id)}">撤销${s.current ? "并退出" : ""}</button></div><p>${esc(s.device)}</p><p>登录 ${time(s.created_at * 1000)} · 最近活动 ${time(s.last_seen * 1000)}</p></article>`).join("")}</div></section><section class="panel"><div class="panel-header"><h2>修改密码</h2></div><form class="panel-body" id="password-form" novalidate>${field("old-password", "当前密码", "password", "current-password")}${field("new-password", "新密码", "password", "new-password")}${field("new-password-again", "再次输入新密码", "password", "new-password")}<p class="field-help">新密码至少 14 个字符；成功后所有设备会话立即撤销。</p><div class="form-error" id="password-error" role="alert"></div><button type="submit" class="button primary">修改密码并退出</button></form></section></div><section class="panel section-gap"><div class="panel-header"><h2>最近安全事件</h2><span class="tag">最多 100 条 · 不记录密码、代码或账户金额</span></div><div class="panel-body audit-events">${audit.events.map((e) => `<div class="audit-event"><time>${time(e.occurred_at * 1000)}</time><strong>${esc(e.action)}</strong><span>${esc(e.target)}</span></div>`).join("") || empty("暂无安全事件", "登录与敏感操作会出现在这里。")}</div></section></div>`;
}
export function mountSecurityPage(onRefresh) {
  document.querySelector("#security-logout").onclick = signOut;
  revealButtons(document.querySelector("#password-form"));
  document.querySelector("#password-form").onsubmit = (e) => {
    e.preventDefault();
    if (composing) return;
    submit(e.target, async (values) => {
      if (values["new-password"] !== values["new-password-again"])
        throw Error("两次新密码不一致");
      if (values["new-password"].length < 14)
        throw Error("新密码至少 14 个字符");
      await request("/auth/password", {
        method: "POST",
        body: {
          password: values["old-password"],
          new_password: values["new-password"],
        },
      });
      e.target.reset();
      identity = null;
      document.dispatchEvent(new CustomEvent("finch:signed-out"));
      loginForm("密码已更新，请使用新密码登录。");
    });
  };
  for (const button of document.querySelectorAll("[data-revoke-session]"))
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await request(
          "/auth/sessions/" + encodeURIComponent(button.dataset.revokeSession),
          { method: "DELETE" },
        );
        if (result.current) {
          identity = null;
          document.dispatchEvent(new CustomEvent("finch:signed-out"));
          loginForm("当前会话已撤销。");
        } else {
          notify("会话已撤销");
          onRefresh();
        }
      } catch (error) {
        notify(error.message);
        button.disabled = false;
      }
    };
}

// Lock the displayed workspace even when no request is currently in flight.
setInterval(() => {
  if (
    identity &&
    !identity.setup_required &&
    Date.now() - lastActivity > identity.idle_seconds * 1000
  ) {
    identity = null;
    document.dispatchEvent(new CustomEvent("finch:locked"));
    loginForm("闲置时间已到，请重新登录后继续。未发送草稿仍保留在本页内存中。");
  }
}, 15000);
