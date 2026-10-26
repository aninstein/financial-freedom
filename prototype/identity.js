import { request, configureSecurity } from "./api.js";
import { esc, icon, showDialog, notify, time, empty } from "./ui.js";
let identity = null,
  lastActivity = Date.now(),
  pendingReady = null,
  reauthPending = null,
  readyPromise = null;
let composing = false;
let smsTimer = null,
  authView = 0;
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
  clearInterval(smsTimer);
  smsTimer = null;
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
    "输入账户和密码即可登录。已启用短信保护时，会在下一步验证。",
    `${message ? `<div class="alert">${esc(message)}</div>` : ""}<form id="login-form" novalidate>${field("username", "账号", "text", "username")}${field("password", "密码", "password", "current-password")}<div class="form-error" id="login-error" role="alert"></div><button class="button primary" type="submit">登录</button></form><details class="section-gap"><summary>无法登录或尚未创建账户</summary><p class="field-help">账户由本人在本机终端创建，系统未开放公共注册。</p><code>.venv/bin/python -m app.manage init-owner</code><p class="field-help">忘记密码可在项目终端运行 .venv/bin/python -m app.manage reset-password。短信登录由服务端ENV配置启用。</p></details>`,
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
      if (result.requires_sms) {
        identity = null;
        smsLogin(result, values.username);
      } else {
        identity = result;
        ready();
      }
    });
  };
  form.querySelector("#username").focus();
}
function smsLogin(challenge, username) {
  showRoot();
  const view = authView;
  let cooldown = 0,
    sending = false;
  root().innerHTML = frame(
    "短信验证",
    `账号密码已验证，验证码将发送至 ${challenge.masked_phone}。`,
    `<p class="field-help">点击发送后，填写手机收到的6位短信验证码即可登录，无需安装手机App。</p><form id="sms-login-form" novalidate class="section-gap">${field("sms-code", "短信验证码", "text", "one-time-code")}<div class="actions"><button class="button" type="button" id="send-sms">发送验证码</button><span class="field-help" id="sms-expiry"></span></div><p class="form-error" id="sms-send-error" role="alert"></p><p class="field-help" id="sms-status" role="status"></p><div class="form-error" id="sms-error" role="alert"></div><button type="submit" class="button primary">验证并登录</button></form><button type="button" class="button ghost section-gap" id="sms-back">返回账号密码</button>`,
  );
  const form = document.querySelector("#sms-login-form"),
    send = document.querySelector("#send-sms"),
    submitButton = form.querySelector("button[type=submit]");
  const code = form.querySelector("#sms-code");
  code.inputMode = "numeric";
  code.maxLength = 6;
  const update = () => {
    if (view !== authView) {
      clearInterval(smsTimer);
      return;
    }
    const remaining = Math.max(
      0,
      Math.ceil(challenge.expires_at - Date.now() / 1000),
    );
    const wait = Math.max(0, Math.ceil(cooldown - Date.now() / 1000));
    send.disabled = sending || wait > 0 || remaining === 0;
    send.textContent = sending
      ? "正在发送…"
      : wait > 0
        ? `${wait} 秒后可重发`
        : "发送验证码";
    document.querySelector("#sms-expiry").textContent = remaining
      ? `本次验证剩余 ${Math.floor(remaining / 60)}分${remaining % 60}秒`
      : "本次验证已过期，请返回重新登录。";
    if (!remaining) submitButton.disabled = true;
  };
  send.onclick = async () => {
    if (sending) return;
    sending = true;
    cooldown = Date.now() / 1000 + 60;
    update();
    document.querySelector("#sms-send-error").textContent = "";
    try {
      const result = await request("/auth/sms/send", {
        method: "POST",
        body: { challenge_id: challenge.challenge_id },
        timeout: 16000,
      });
      if (view !== authView) return;
      document.querySelector("#sms-status").textContent = result.message;
      code.focus();
    } catch (error) {
      if (view === authView)
        document.querySelector("#sms-send-error").textContent = error.message;
    } finally {
      sending = false;
      if (view === authView) update();
    }
  };
  form.onsubmit = (e) => {
    e.preventDefault();
    if (composing || e.isComposing) return;
    submit(form, async (values) => {
      if (!/^\d{6}$/.test(values["sms-code"]))
        throw Error("请输入6位短信验证码");
      const result = await request("/auth/sms/verify", {
        method: "POST",
        body: {
          challenge_id: challenge.challenge_id,
          code: values["sms-code"],
        },
      });
      code.value = "";
      if (view !== authView) return;
      clearInterval(smsTimer);
      identity = result;
      ready();
    });
  };
  document.querySelector("#sms-back").onclick = () => loginForm("", username);
  smsTimer = setInterval(update, 1000);
  update();
  code.focus();
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
      `<div class="alert">创建密码需在本机终端输入，不写入 ENV 或仓库。</div><pre class="code-data section-gap">cd /Users/bytedance/my-git/financial-freedom\n.venv/bin/python -m app.manage init-owner</pre><p class="field-help">密码至少14个字符；创建后即可用账号密码登录，短信验证可按需配置。</p><button class="button primary section-gap" id="check-owner">我已创建账户，继续登录</button>`,
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
  return `<div class="content-page"><div class="page-heading"><div><h1>账户安全</h1><p>管理私人空间的身份、会话和访问记录。</p></div><button class="button" id="security-logout">退出登录</button></div><div class="stat-grid"><div class="stat"><div class="stat-label">当前账户</div><div class="stat-value">${esc(me.user.username)}</div><div class="stat-note">唯一拥有者</div></div><div class="stat"><div class="stat-label">登录方式</div><div class="stat-value">${me.login_verification === "sms" ? "密码 + 短信" : "账号密码"}</div><div class="stat-note">交易确认仅重验账户密码</div></div><div class="stat"><div class="stat-label">会话最长有效期</div><div class="stat-value">8 小时</div><div class="stat-note">闲置 ${Math.floor(me.idle_seconds / 60)} 分钟退出</div></div><div class="stat"><div class="stat-label">公开注册</div><div class="stat-value">已关闭</div><div class="stat-note">账户由本机终端管理</div></div></div><section class="panel section-gap"><div class="panel-header"><h2>短信登录保护</h2><span class="tag">${me.sms.configured ? "已配置服务" : "未配置"}</span></div><div class="panel-body"><p class="field-help">当前${me.login_verification === "sms" ? "已启用登录短信验证" : "使用密码登录，短信为可选配置"}。火山短信凭据、消息组、已审核签名、模板和本人手机号由服务端ENV管理，页面不显示密钥或完整手机号。</p><p class="field-help section-gap">${me.sms.configured ? "短信仅在本人通过密码后主动点击发送。" : "配置说明：项目 docs/SMS_SETUP.md。未配置短信不影响默认密码登录。"}</p></div></section><div class="split section-gap"><section class="panel"><div class="panel-header"><h2>登录设备与会话</h2></div><div class="panel-body">${sessions.map((s) => `<article class="provider-item section-gap"><div><strong>${s.current ? "当前会话" : "其他会话"}</strong><button class="button small" data-revoke-session="${s.current ? "current" : esc(s.id)}">撤销${s.current ? "并退出" : ""}</button></div><p>${esc(s.device)}</p><p>登录 ${time(s.created_at * 1000)} · 最近活动 ${time(s.last_seen * 1000)}</p></article>`).join("")}</div></section><section class="panel"><div class="panel-header"><h2>修改密码</h2></div><form class="panel-body" id="password-form" novalidate>${field("old-password", "当前密码", "password", "current-password")}${field("new-password", "新密码", "password", "new-password")}${field("new-password-again", "再次输入新密码", "password", "new-password")}<p class="field-help">新密码至少 14 个字符；成功后所有设备会话立即撤销。</p><div class="form-error" id="password-error" role="alert"></div><button type="submit" class="button primary">修改密码并退出</button></form></section></div><section class="panel section-gap"><div class="panel-header"><h2>最近安全事件</h2><span class="tag">最多 100 条 · 不记录密码、代码或账户金额</span></div><div class="panel-body audit-events">${audit.events.map((e) => `<div class="audit-event"><time>${time(e.occurred_at * 1000)}</time><strong>${esc(e.action)}</strong><span>${esc(e.target)}</span></div>`).join("") || empty("暂无安全事件", "登录与敏感操作会出现在这里。")}</div></section></div>`;
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
