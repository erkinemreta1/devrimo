import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getProfile, patchProfile } from "@/lib/api/profile";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";
import type { ProfileInput } from "@/lib/types";

export async function GET() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await getProfile(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function PATCH(request: NextRequest) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const body = (await request.json()) as ProfileInput;
    return NextResponse.json(await patchProfile(result.auth.accessToken, body));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
