async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/admin/${path.replace(/^\//, "")}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail;
    const nested = detail && typeof detail === "object" ? detail.detail : null;
    throw new Error(nested || payload?.error || detail || `Request failed (${response.status})`);
  }
  return payload as T;
}

export function adminGet<T>(path: string) {
  return adminFetch<T>(path);
}

export function adminMutate<T>(path: string, method: "POST" | "PUT" | "DELETE", body: unknown) {
  return adminFetch<T>(path, { method, body: JSON.stringify(body) });
}
