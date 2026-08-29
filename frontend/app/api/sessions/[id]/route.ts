import { NextResponse } from "next/server";
import { deleteChatSession, getChatSession } from "@/lib/api/chat";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

type RouteContext = { params: Promise<{ id: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const { id } = await context.params;
    const session = await getChatSession(result.auth.accessToken, id);
    return NextResponse.json(session);
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function DELETE(_request: Request, context: RouteContext) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const { id } = await context.params;
    await deleteChatSession(result.auth.accessToken, id);
    return NextResponse.json({ ok: true });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
