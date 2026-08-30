import { PostHog } from "posthog-node";
import { getPostHogHost, getPostHogKey } from "@/lib/env";

let client: PostHog | null = null;
let warned = false;

/**
 * The server-side PostHog client for route handlers and `instrumentation.ts`.
 *
 * Returns `null` when unconfigured so every call site is a safe optional call.
 * Next.js server functions are short-lived and can be torn down between
 * requests, so events are flushed immediately rather than batched — a batched
 * exception report that never flushes is the same as no error tracking.
 */
export function getPostHogServer(): PostHog | null {
  const key = getPostHogKey();
  if (!key) {
    if (!warned && process.env.NODE_ENV !== "production") {
      warned = true;
      console.error(
        "NEXT_PUBLIC_POSTHOG_KEY variable required by PostHog is missing or un-configured, " +
          "this causes events to be silently missed. This error stops appearing once " +
          "NEXT_PUBLIC_POSTHOG_KEY is configured",
      );
    }
    return null;
  }

  if (!client) {
    client = new PostHog(key, {
      host: getPostHogHost(),
      flushAt: 1,
      flushInterval: 0,
    });
  }
  return client;
}

const POSTHOG_COOKIE = /ph_phc_.*?_posthog=([^;]+)/;

/**
 * The browser's distinct id, read from PostHog's own cookie.
 *
 * Used only to attribute server-side events to the same person as the client's
 * — never as an authorization signal. The broker derives identity from the
 * verified Supabase JWT instead.
 */
export function distinctIdFromCookies(cookieHeader: string | string[] | undefined): string | null {
  if (!cookieHeader) return null;
  const cookies = Array.isArray(cookieHeader) ? cookieHeader.join("; ") : cookieHeader;
  const match = cookies.match(POSTHOG_COOKIE);
  if (!match?.[1]) return null;
  try {
    return (JSON.parse(decodeURIComponent(match[1])) as { distinct_id?: string }).distinct_id ?? null;
  } catch {
    return null;
  }
}

/** The PostHog session and distinct id the browser attached via `tracing_headers`. */
export function tracingHeadersFrom(request: Request): Record<string, string> {
  const forwarded: Record<string, string> = {};
  for (const name of ["x-posthog-distinct-id", "x-posthog-session-id"]) {
    const value = request.headers.get(name);
    if (value) forwarded[name] = value;
  }
  return forwarded;
}
