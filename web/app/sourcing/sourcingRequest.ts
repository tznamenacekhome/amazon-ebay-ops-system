"use client";

export async function sourcingRequest(
  input: RequestInfo | URL,
  init: RequestInit = {},
  transport: typeof fetch = (...args) => fetch(...args),
): Promise<Response> {
  const readOnly = !init.method || init.method.toUpperCase() === "GET";
  for (let attempt = 0; ; attempt++) {
    let response: Response;
    try {
      // An expired ALB session redirects to Cognito. Following that redirect
      // inside fetch produces an opaque CORS error rather than a usable login.
      response = await transport(input, { ...init, redirect: "manual" });
    } catch (error) {
      if (readOnly && attempt === 0 && !init.signal?.aborted) continue;
      throw new Error(readOnly
        ? "Could not reach MBOP. Check your connection. Reload this page to reconnect or sign in."
        : "The save response was interrupted. The change may have saved. Reload this page to reconnect or sign in, then check the opportunity before trying again.", { cause: error });
    }
    if (response.type === "opaqueredirect" || response.status === 401 || response.status === 302) {
      throw new Error(readOnly
        ? "Your MBOP session needs sign-in. Reload this page to sign in again."
        : "Your MBOP session needs sign-in. The save is not confirmed. Reload this page to sign in, then check the opportunity before trying again.");
    }
    // Preserve structured API errors; identify login HTML without attempting JSON.
    if ((response.headers.get("content-type") ?? "").toLowerCase().includes("text/html")) {
      throw new Error("MBOP returned a sign-in or unavailable page. Reload this page to reconnect or sign in; check the opportunity before retrying a save.");
    }
    try {
      const text = await response.text();
      const body = [204, 205, 304].includes(response.status) ? null : text;
      return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
    } catch (error) {
      if (readOnly && attempt === 0 && !init.signal?.aborted) continue;
      throw new Error(readOnly
        ? "Could not read the MBOP response. Reload this page to reconnect or sign in."
        : "The save response was interrupted. The change may have saved. Reload this page to reconnect or sign in, then check the opportunity before trying again.", { cause: error });
    }
  }
}
