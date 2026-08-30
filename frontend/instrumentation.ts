/**
 * Server-side error capture for the Next.js layer.
 *
 * `onRequestError` fires for every route handler, server component and RSC
 * render that throws — all 17 handlers under `app/api/**` included — so this
 * one hook is the difference between a 500 that is investigable and one that
 * only ever existed in a container log.
 */

import type { Instrumentation } from "next";

export function register() {
  // Initialisation happens lazily in `lib/posthog-server.ts`; nothing to do
  // here, but Next expects this export alongside onRequestError.
}

export const onRequestError: Instrumentation.onRequestError = async (error, request, context) => {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  try {
    const { getPostHogServer, distinctIdFromCookies } = await import("@/lib/posthog-server");
    const posthog = getPostHogServer();
    if (!posthog) return;

    // React can replace the thrown instance during Server Component rendering,
    // in which case `digest` is the only stable handle on the real error.
    const digest =
      typeof error === "object" && error !== null && "digest" in error ? String(error.digest) : undefined;

    posthog.captureException(
      error instanceof Error ? error : new Error(String(error)),
      distinctIdFromCookies(request.headers.cookie) ?? undefined,
      {
        source: "next_request",
        path: request.path,
        method: request.method,
        digest,
        router_kind: context.routerKind,
        route_path: context.routePath,
        route_type: context.routeType,
      },
    );
    // Awaited deliberately: the handler's lifetime is the only window in which
    // this is guaranteed to send.
    await posthog.flush();
  } catch {
    // An error reporter that throws would turn one 500 into two.
  }
};
