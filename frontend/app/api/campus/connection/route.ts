import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  deleteCampusConnection,
  getCampusConnection,
  putCampusConnection,
} from "@/lib/api/campus";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";
import type { CampusConnectionInput } from "@/lib/types";

export async function GET() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await getCampusConnection(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

/**
 * The student's METU password passes through this handler on its way to the
 * broker, and is never logged, cached, or echoed back — the broker's response
 * describes the connection without containing it.
 */
export async function PUT(request: NextRequest) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const body = (await request.json()) as CampusConnectionInput;
    return NextResponse.json(await putCampusConnection(result.auth.accessToken, body));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function DELETE() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    return NextResponse.json(await deleteCampusConnection(result.auth.accessToken));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
