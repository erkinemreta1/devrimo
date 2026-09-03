import { ApiError } from "@/lib/api/errors";

/**
 * Client-side fetch for this app's own /api routes.
 *
 * Error extraction lives here for browser routes, authenticated broker calls,
 * and admin calls so every surface handles the same response shape.
 */
export type JsonFetchInit = Omit<RequestInit, "body"> & { body?: unknown };

export function apiErrorMessage(status: number, payload: unknown): string {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    for (const key of ["detail", "error", "message"] as const) {
      const value = record[key];
      if (typeof value === "string" && value.trim()) return value;
      if (value && typeof value === "object") {
        const nested = apiErrorMessage(status, value);
        if (nested !== `Request failed (${status})`) return nested;
      }
    }
  }
  return `Request failed (${status})`;
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  return new ApiError(apiErrorMessage(response.status, payload), response.status, payload);
}

export async function jsonFetch<T>(path: string, init: JsonFetchInit = {}): Promise<T> {
  const { body, headers, ...rest } = init;

  const response = await fetch(path, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  return payload as T;
}
