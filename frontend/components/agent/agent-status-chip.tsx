"use client";

import { useAgent } from "@/hooks/useAgent";
import { Badge } from "@/components/ui/badge";
import type { AgentStatus } from "@/lib/types";
import { useLocale } from "@/components/locale-provider";

export function AgentStatusChip() {
  const { locale } = useLocale();
  const { agent } = useAgent();
  if (!agent) return null;
  const statusLabel: Record<AgentStatus, Record<"tr" | "en", string>> = {
    provisioning: { tr: "Hazırlanıyor", en: "Preparing" },
    running: { tr: "Hazır", en: "Ready" },
    stopped: { tr: "Durduruldu", en: "Stopped" },
    error: { tr: "Hata", en: "Error" },
    destroying: { tr: "Siliniyor", en: "Removing" },
  };

  return (
    <Badge role="status" aria-live="polite" variant={agent.status === "running" ? "default" : "secondary"}>
      {statusLabel[agent.status][locale]}
    </Badge>
  );
}
