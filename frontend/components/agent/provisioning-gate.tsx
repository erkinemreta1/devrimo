"use client";

import { useEffect, useRef } from "react";
import { Loader2Icon } from "lucide-react";
import { useAgent } from "@/hooks/useAgent";
import { Button } from "@/components/ui/button";
import type { ReactNode } from "react";
import { useLocale } from "@/components/locale-provider";

export function ProvisioningGate({ children }: { children: ReactNode }) {
  const { pick } = useLocale();
  const { agent, error, ensureRunning } = useAgent();
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;
    ensureRunning.mutate();
  }, [ensureRunning]);

  if (ensureRunning.isPending || (!agent && !error)) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        <div>
          <p className="font-medium">{pick({ tr: "Asistanın hazırlanıyor", en: "Setting up your assistant" })}</p>
          <p className="text-sm text-muted-foreground">
            {pick({ tr: "Kişisel çalışma alanın başlatılıyor. Bu işlem kısa sürebilir.", en: "Your personal workspace is starting. This may take a moment." })}
          </p>
        </div>
      </div>
    );
  }

  if (agent?.status === "error" || error) {
    const message = agent?.error_detail || (error instanceof Error ? error.message : "Your agent could not be started.");
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <div>
          <p className="font-medium">{pick({ tr: "Asistana ulaşılamıyor", en: "Assistant unavailable" })}</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">{message}</p>
        </div>
        <Button onClick={() => { ensureRunning.reset(); ensureRunning.mutate(); }}>
          {pick({ tr: "Tekrar dene", en: "Try again" })}
        </Button>
      </div>
    );
  }

  if (agent?.status !== "running") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{pick({ tr: "Asistanın hazırlanıyor…", en: "Preparing your assistant…" })}</p>
      </div>
    );
  }

  return <div className="h-full min-h-0">{children}</div>;
}
