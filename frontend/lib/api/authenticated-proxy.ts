import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/env";
import { requireAuth } from "@/lib/api/route-utils";

export type ProxyContext = { params: Promise<{ path: string[] }> };

export async function proxyAuthenticatedRequest(
  request: NextRequest,
  context: ProxyContext,
  namespace: "admin" | "schedule" | "student",
) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  const { path } = await context.params;
  const safePath = path.map(encodeURIComponent).join("/");
  const upstream = `${getApiBaseUrl()}/api/v1/${namespace}/${safePath}${request.nextUrl.search}`;
  const hasBody = request.method !== "GET" && request.method !== "HEAD" && request.body !== null;
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: {
      Accept: request.headers.get("accept") ?? "application/json",
      Authorization: `Bearer ${result.auth.accessToken}`,
      ...(hasBody ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {}),
    },
    body: hasBody ? request.body : undefined,
    cache: "no-store",
  };
  if (hasBody) init.duplex = "half";
  const response = await fetch(upstream, init);

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
