import { NextResponse } from "next/server";
import { getMyAgent, provisionAgent, startAgent } from "@/lib/api/agents";
import { isNotFound } from "@/lib/api/errors";
import { apiErrorResponse, requireAuth } from "@/lib/api/route-utils";
import type { Agent } from "@/lib/types";

const wait = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function ensureRunning(token: string) {
  let agent: Agent;
  try {
    agent = await getMyAgent(token);
  } catch (error) {
    if (!isNotFound(error)) throw error;
    agent = await provisionAgent(token);
  }

  // An earlier failed build leaves the entitlement in `error`. Retry the
  // actual backend start path so a transient/local configuration failure can
  // recover instead of returning the stale error forever.
  if (agent.status === "stopped" || agent.status === "error") return startAgent(token);
  if (agent.status !== "provisioning") return agent;

  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    await wait(500);
    agent = await getMyAgent(token);
    if (agent.status === "running" || agent.status === "error") return agent;
    if (agent.status === "stopped") return startAgent(token);
  }

  throw new Error("Assistant workspace did not become ready in time.");
}

export async function POST() {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  try {
    const agent = await ensureRunning(result.auth.accessToken);
    return NextResponse.json(agent);
  } catch (error) {
    return apiErrorResponse(error);
  }
}
