"use client";

import { toast } from "sonner";
import { Loader2Icon } from "lucide-react";
import { useAgent } from "@/hooks/useAgent";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export function SettingsClient() {
  const { agent, isLoading, start, stop, destroy, provision, refetch } = useAgent();

  async function run(action: () => Promise<unknown>, success: string) {
    try {
      await action();
      toast.success(success);
      await refetch();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Action failed");
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your dedicated Hermes agent.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Agent</CardTitle>
          <CardDescription>One isolated container per account. Destroying it removes container data.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Loading agent status…
            </div>
          ) : agent ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{agent.status}</Badge>
                <span className="text-sm text-muted-foreground">ID {agent.id}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={start.isPending || agent.status === "running"}
                  onClick={() => run(() => start.mutateAsync(), "Agent started")}
                >
                  Start
                </Button>
                <Button
                  variant="outline"
                  disabled={stop.isPending || agent.status !== "running"}
                  onClick={() => run(() => stop.mutateAsync(), "Agent stopped")}
                >
                  Stop
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger render={<Button variant="destructive" />}>
                    Destroy
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Destroy this agent?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This stops the container and deletes its volume. You can provision a new agent afterwards.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => run(() => destroy.mutateAsync(), "Agent destroyed")}
                      >
                        Destroy
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-muted-foreground">No agent is provisioned for this account.</p>
              <Button onClick={() => run(() => provision.mutateAsync(), "Provisioning started")}>
                Create agent
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
