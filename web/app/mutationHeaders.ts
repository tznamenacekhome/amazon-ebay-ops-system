"use client";

export function mutationHeaders(headers: HeadersInit = {}) {
  return {
    ...headers,
    "x-mbop-csrf": "1",
  };
}
