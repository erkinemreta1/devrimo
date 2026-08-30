/**
 * Client-side fetch for this app's own /api routes.
 *
 * Those routes answer with `{ error }` on failure (see lib/api/route-utils.ts),
 * so the thrown Error carries the broker's message rather than a bare status —
 * onboarding shows these strings directly to the student.
 */
export type JsonFetchInit = Omit<RequestInit, "body"> & { body?: unknown };

export class RequestFailedError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "RequestFailedError";
    this.status = status;
  }
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

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message =
      payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
        ? payload.error
        : response.statusText || `Request failed (${response.status})`;
    throw new RequestFailedError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
