import { NextResponse } from "next/server";
import { getAuth } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/env";
import { ApiError } from "@/lib/api/errors";
import { getPostHogServer } from "@/lib/posthog-server";

export async function requireAuth() {
  if (!isSupabaseConfigured()) {
    return { error: NextResponse.json({ error: "Supabase is not configured" }, { status: 503 }) };
  }

  const auth = await getAuth();
  if (!auth?.accessToken) {
    return { error: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  }

  return { auth };
}

export function apiErrorResponse(error: unknown) {
  if (error instanceof ApiError) {
    // 4xx from the broker is expected control flow — a missing session, a busy
    // agent — and reporting it would drown the real failures. 5xx is not.
    if (error.status >= 500) {
      getPostHogServer()?.captureException(error, undefined, {
        source: "api_proxy",
        status: error.status,
      });
    }
    return NextResponse.json(
      { error: error.message, detail: error.body },
      { status: error.status },
    );
  }

  // Anything that is not an ApiError never reached the broker at all: a
  // network failure, a bug in a route handler, a malformed response.
  const message = error instanceof Error ? error.message : "Unexpected error";
  getPostHogServer()?.captureException(error instanceof Error ? error : new Error(message), undefined, {
    source: "api_proxy",
    status: 502,
  });
  return NextResponse.json({ error: message }, { status: 502 });
}
