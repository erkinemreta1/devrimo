import { apiFetch } from "@/lib/api/client";
import type { Agent } from "@/lib/types";

export function getMyAgent(token: string) {
  return apiFetch<Agent>("/agents/me", { token });
}

export function provisionAgent(token: string) {
  return apiFetch<Agent>("/agents/provision", { method: "POST", token, body: {} });
}

export function startAgent(token: string) {
  return apiFetch<Agent>("/agents/start", { method: "POST", token, body: {} });
}

export function stopAgent(token: string) {
  return apiFetch<Agent>("/agents/stop", { method: "POST", token, body: {} });
}

export function destroyAgent(token: string) {
  return apiFetch<void>("/agents", { method: "DELETE", token });
}
