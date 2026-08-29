import { NextResponse } from "next/server";
import { provisionAgent } from "@/lib/api/agents";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function POST() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const agent = await provisionAgent(result.auth.accessToken);
    return NextResponse.json(agent, { status: 201 });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
