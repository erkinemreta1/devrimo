"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Agent } from "@/lib/types";

async function parseError(response: Response) {
  const body = await response.json().catch(() => null);
  const message =
    (body && typeof body === "object" && "error" in body && typeof body.error === "string"
      ? body.error
      : null) || response.statusText;
  const error = new Error(message) as Error & { status: number };
  error.status = response.status;
  throw error;
}

async function fetchAgent(): Promise<Agent | null> {
  const response = await fetch("/api/agents/me");
  if (response.status === 404) return null;
  if (!response.ok) await parseError(response);
  return response.json();
}

async function postAgent(path: string) {
  const response = await fetch(path, { method: "POST" });
  if (!response.ok) await parseError(response);
  return response.json() as Promise<Agent>;
}

export function useAgent() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["agent"],
    queryFn: fetchAgent,
  });

  const ensureRunning = useMutation({
    mutationFn: () => postAgent("/api/agents/ensure-running"),
    onSuccess: (agent) => queryClient.setQueryData(["agent"], agent),
  });

  const stop = useMutation({
    mutationFn: () => postAgent("/api/agents/stop"),
    onSuccess: (agent) => queryClient.setQueryData(["agent"], agent),
  });

  const destroy = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/agents", { method: "DELETE" });
      if (!response.ok) await parseError(response);
    },
    onSuccess: () => queryClient.setQueryData(["agent"], null),
  });

  return {
    agent: query.data ?? null,
    isLoading: query.isLoading,
    error: query.error ?? ensureRunning.error ?? stop.error ?? destroy.error,
    refetch: query.refetch,
    ensureRunning,
    stop,
    destroy,
  };
}
