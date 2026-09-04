import type { NextRequest } from "next/server";
import { proxyAuthenticatedRequest, type ProxyContext } from "@/lib/api/authenticated-proxy";

const proxy = (request: NextRequest, context: ProxyContext) =>
  proxyAuthenticatedRequest(request, context, "schedule");

export const GET = proxy;
export const POST = proxy;
