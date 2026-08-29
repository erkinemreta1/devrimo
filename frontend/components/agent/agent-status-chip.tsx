"use client";

import { useAgent } from "@/hooks/useAgent";
import { Badge } from "@/components/ui/badge";
import type { AgentStatus } from "@/lib/types";

const statusLabel: Record<AgentStatus, string> = {
  provisioning: "Provisioning",
  running: "Running",
  stopped: "Stopped",
  error: "Error",
  destroying: "Destroying",
};

export function AgentStatusChip() {
  const { agent } = useAgent();
  if (!agent) return null;

  return (
    <Badge variant={agent.status === "running" ? "default" : "secondary"}>
      {statusLabel[agent.status]}
    </Badge>
  );
}
