import { NextResponse } from "next/server";
import { applyCampusConnection } from "@/lib/api/campus";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function POST() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await applyCampusConnection(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
