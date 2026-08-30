import { NextResponse } from "next/server";
import { continueChatRun, type ChatConfirmation } from "@/lib/api/chat";
import { requireAuth } from "@/lib/api/route-utils";
import { tracingHeadersFrom } from "@/lib/posthog-server";

export const maxDuration = 600;

export async function POST(request: Request) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  const body = (await request.json()) as {
    confirmation?: ChatConfirmation;
    requirement_id?: string;
    approved?: boolean;
  };
  if (!body.confirmation || !body.requirement_id || typeof body.approved !== "boolean") {
    return NextResponse.json({ detail: "Invalid confirmation request" }, { status: 422 });
  }

  try {
    const continuation = await continueChatRun(
      result.auth.accessToken,
      body.confirmation,
      body.requirement_id,
      body.approved,
      tracingHeadersFrom(request),
    );
    return NextResponse.json(continuation);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Confirmation failed";
    return NextResponse.json({ detail: message }, { status: 502 });
  }
}
