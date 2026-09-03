import { getApiBaseUrl } from "@/lib/env";
import { jsonFetch } from "@/lib/api/fetcher";

export type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown;
  token: string;
};

export async function apiFetch<T>(path: string, init: ApiRequestInit): Promise<T> {
  const { token, body, headers, ...rest } = init;
  const url = `${getApiBaseUrl()}/api/v1${path.startsWith("/") ? path : `/${path}`}`;

  return jsonFetch<T>(url, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...headers,
    },
    body,
  });
}
