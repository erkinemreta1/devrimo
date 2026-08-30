import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { verifyCampusCredentials } from "@/lib/api/campus";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function POST(request: NextRequest) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const body = (await request.json()) as { metu_username: string; metu_password: string };
    return NextResponse.json(await verifyCampusCredentials(result.auth.accessToken, body));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
