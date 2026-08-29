import { NextResponse } from "next/server";
import { listChatSessions } from "@/lib/api/chat";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function GET() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const sessions = await listChatSessions(result.auth.accessToken);
    return NextResponse.json({ sessions });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
