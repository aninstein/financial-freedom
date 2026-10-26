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
export async function postOrder(body, key) {
  return request("/paper/orders", {
    method: "POST",
    body,
    headers: { "Idempotency-Key": key },
    timeout: 30000,
  });
}
