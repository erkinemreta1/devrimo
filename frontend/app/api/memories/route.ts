import { NextResponse } from "next/server";
import { clearMemories, listMemories } from "@/lib/api/memories";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function GET() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await listMemories(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function DELETE() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await clearMemories(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
