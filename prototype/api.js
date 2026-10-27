let security = {
  csrf: () => null,
  active: () => false,
  expired: () => {},
  reauthenticate: async () => false,
};
export function configureSecurity(handlers) {
  security = { ...security, ...handlers };
}
export const API = "/api/v1";
export async function request(
  path,
  {
    method = "GET",
    body,
    signal,
    timeout = 30000,
    headers: extraHeaders = {},
    _reauthenticated = false,
  } = {},
) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(
    () =>
      controller.abort(
        new DOMException("请求超时，请稍后重试", "TimeoutError"),
      ),
    timeout,
  );
  try {
    const headers = { ...extraHeaders };
    if (security.active()) headers["X-Finch-Active"] = "1";
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && security.csrf())
      headers["X-CSRF-Token"] = security.csrf();
    let data = body;
    if (body !== undefined && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      data = JSON.stringify(body);
    }
    const res = await fetch(API + path, {
      method,
      body: data,
      headers,
      signal: controller.signal,
    });
    const result = await res.json().catch(() => ({}));
    if (controller.signal.aborted)
      throw (
        controller.signal.reason || new DOMException("请求已取消", "AbortError")
      );
    if (!res.ok) {
      const code =
        typeof result.detail === "object" ? result.detail?.code : null;
      if (
        res.status === 428 &&
        code === "REAUTH_REQUIRED" &&
        !_reauthenticated
      ) {
        if (await security.reauthenticate())
          return request(path, {
            method,
            body,
            signal,
            timeout,
            headers: extraHeaders,
            _reauthenticated: true,
          });
      }
      if (
        res.status === 401 &&
        (!path.startsWith("/auth/") || code === "SESSION_EXPIRED")
      )
        security.expired();
      const error = new Error(
        typeof result.detail === "string"
          ? result.detail
          : result.detail?.message || "请求未完成，请检查输入后重试",
      );
      error.code = code;
      error.status = res.status;
      throw error;
    }
    return result;
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted)
      throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

export async function requestEvents(path, { body, onEvent, timeout = 190000, _reauthenticated = false } = {}) {
  const controller = new AbortController();
  let reader;
  const timer = setTimeout(() => controller.abort(new DOMException("请求超时，请稍后重试", "TimeoutError")), timeout);
  try {
    const headers = { "Content-Type": "application/json", "Accept": "text/event-stream" };
    if (security.active()) headers["X-Finch-Active"] = "1";
    if (security.csrf()) headers["X-CSRF-Token"] = security.csrf();
    const res = await fetch(API + path, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    if (!res.ok) {
      const result = await res.json().catch(() => ({}));
      const code = typeof result.detail === "object" ? result.detail?.code : null;
      if (res.status === 428 && code === "REAUTH_REQUIRED" && !_reauthenticated && await security.reauthenticate())
        return requestEvents(path, { body, onEvent, timeout, _reauthenticated: true });
      if (res.status === 401 && (!path.startsWith('/auth/') || code === 'SESSION_EXPIRED')) security.expired();
      throw new Error(typeof result.detail === "string" ? result.detail : result.detail?.message || "请求未完成，请检查输入后重试");
    }
    if (!res.body) throw new Error("浏览器不支持流式响应，请更新浏览器后重试。");
    reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const payload = frame.split("\n").filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
        if (payload) await onEvent(JSON.parse(payload));
      }
      if (done) break;
    }
  } catch (error) {
    if (controller.signal.aborted) throw new Error("请求超时，请稍后重试");
    throw error;
  } finally {
    if (reader) reader.cancel().catch(() => {});
    clearTimeout(timer);
  }
}
export async function postOrder(body, key) {
  return request("/paper/orders", {
    method: "POST",
    body,
    headers: { "Idempotency-Key": key },
    timeout: 30000,
  });
}
