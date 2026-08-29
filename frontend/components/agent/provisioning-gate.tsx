"use client";

import { useEffect, useRef } from "react";
import { Loader2Icon } from "lucide-react";
import { useAgent } from "@/hooks/useAgent";
import { Button } from "@/components/ui/button";
import type { ReactNode } from "react";

export function ProvisioningGate({ children }: { children: ReactNode }) {
  const { agent, isLoading, error, provision, start, refetch } = useAgent();
  const attempted = useRef(false);

  useEffect(() => {
    if (isLoading || attempted.current) return;

    if (!agent) {
      attempted.current = true;
      provision.mutate();
      return;
    }

    if (agent.status === "stopped") {
      attempted.current = true;
      start.mutate();
    }
  }, [agent, isLoading, provision, start]);

  useEffect(() => {
    if (agent?.status === "running") {
      attempted.current = false;
    }
  }, [agent?.status]);

  if (isLoading || provision.isPending || start.isPending || agent?.status === "provisioning") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        <div>
          <p className="font-medium">Setting up your agent</p>
          <p className="text-sm text-muted-foreground">
            Provisioning a dedicated Hermes container. This can take a few seconds.
          </p>
        </div>
      </div>
    );
  }

  if (agent?.status === "error" || error) {
    const message = error instanceof Error ? error.message : "Your agent could not be started.";
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <div>
          <p className="font-medium">Agent unavailable</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">{message}</p>
        </div>
        <Button
          onClick={() => {
            attempted.current = false;
            refetch();
            provision.reset();
            start.reset();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!agent || agent.status !== "running") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Waiting for your agent…</p>
      </div>
    );
  }

  return <div className="h-full min-h-0">{children}</div>;
}
