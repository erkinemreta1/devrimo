import { getApiBaseUrl } from "@/lib/env";
import { ApiError } from "@/lib/api/errors";

export type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  token: string;
};

function errorMessage(status: number, body: unknown) {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    if (typeof record.message === "string") return record.message;
    if (typeof record.error === "string") return record.error;
  }
  return `Request failed (${status})`;
}

export async function apiFetch<T>(path: string, init: ApiRequestInit): Promise<T> {
  const { token, body, headers, ...rest } = init;
  const url = `${getApiBaseUrl()}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

  const response = await fetch(url, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");

  if (!response.ok) {
    throw new ApiError(errorMessage(response.status, payload), response.status, payload);
  }

  return payload as T;
}

export function asList<T>(data: unknown, keys: string[] = ["items", "sessions", "messages", "data", "results"]): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    for (const key of keys) {
      if (Array.isArray(record[key])) return record[key] as T[];
    }
  }
  return [];
}
