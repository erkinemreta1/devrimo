import { NextResponse } from "next/server";
import { destroyAgent } from "@/lib/api/agents";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function DELETE() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    await destroyAgent(result.auth.accessToken);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
