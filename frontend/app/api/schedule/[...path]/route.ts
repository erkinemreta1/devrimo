import { NextResponse, type NextRequest } from "next/server";
import { apiFetch } from "@/lib/api/client";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";

export async function GET(request: NextRequest, context: RouteContext<"/api/schedule/[...path]">) {
  const result = await requireAuth();
  if ("error" in result) return result.error;
  const { path } = await context.params;
  const query = request.nextUrl.search;
  try {
    return NextResponse.json(await apiFetch(`/schedule/${path.join("/")}${query}`, { token: result.auth.accessToken }));
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(request: NextRequest, context: RouteContext<"/api/schedule/[...path]">) {
  const result = await requireAuth();
  if ("error" in result) return result.error;
  const { path } = await context.params;
  try {
    const body = await request.json();
    return NextResponse.json(await apiFetch(`/schedule/${path.join("/")}`, {
      token: result.auth.accessToken,
      method: "POST",
      body,
    }));
  } catch (error) {
    return apiErrorResponse(error);
  }
}
