import { NextResponse } from "next/server";
import { getAuth } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/env";
import { ApiError } from "@/lib/api/errors";

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
    return NextResponse.json(
      { error: error.message, detail: error.body },
      { status: error.status },
    );
  }

  const message = error instanceof Error ? error.message : "Unexpected error";
  return NextResponse.json({ error: message }, { status: 502 });
}
