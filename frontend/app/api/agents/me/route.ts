import { NextResponse } from "next/server";
import { getMyAgent } from "@/lib/api/agents";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function GET() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const agent = await getMyAgent(result.auth.accessToken);
    return NextResponse.json(agent);
  } catch (error) {
    return apiErrorResponse(error);
  }
}
