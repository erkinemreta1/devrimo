import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";
import { requireAuth } from "@/lib/api/route-utils";

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: Context) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  const { path } = await context.params;
  const safePath = path.map(encodeURIComponent).join("/");
  const upstream = `${getApiBaseUrl()}/api/v1/admin/${safePath}${request.nextUrl.search}`;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const response = await fetch(upstream, {
    method: request.method,
    headers: {
      Accept: request.headers.get("accept") ?? "application/json",
      Authorization: `Bearer ${result.auth.accessToken}`,
      ...(body ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {}),
    },
    body: body || undefined,
    cache: "no-store",
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      ...(response.headers.get("content-disposition")
        ? { "content-disposition": response.headers.get("content-disposition")! }
        : {}),
    },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
