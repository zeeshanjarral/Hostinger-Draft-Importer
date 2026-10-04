function jsonError(message, status = 500) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (!url.pathname.startsWith("/api/")) {
      return env.ASSETS.fetch(request);
    }

    if (!env.BACKEND_URL) {
      return jsonError("Cloudflare BACKEND_URL is not configured.", 500);
    }

    if (!env.BACKEND_SECRET) {
      return jsonError("Cloudflare BACKEND_SECRET is not configured.", 500);
    }

    const backendBase = env.BACKEND_URL.replace(/\/+$/, "");
    const backendUrl = backendBase + url.pathname + url.search;

    const headers = new Headers(request.headers);
    headers.set("x-app-secret", env.BACKEND_SECRET);
    headers.set("x-forwarded-host", url.host);

    // Prevent a browser Host header from being forwarded to the backend.
    headers.delete("host");

    const init = {
      method: request.method,
      headers,
      redirect: "manual"
    };

    if (!["GET", "HEAD"].includes(request.method)) {
      init.body = request.body;
    }

    try {
      const response = await fetch(backendUrl, init);

      const outHeaders = new Headers(response.headers);
      outHeaders.set("cache-control", "no-store");

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: outHeaders
      });
    } catch (error) {
      return jsonError(
        "Could not reach the email backend. Check BACKEND_URL and make sure the Render/Railway service is running. " +
        (error?.message || String(error)),
        502
      );
    }
  }
};
