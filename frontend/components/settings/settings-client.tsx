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
import { useLocale } from "@/components/locale-provider";
import { CampusConnectionCard } from "@/components/settings/campus-connection-card";
import { useProfile } from "@/hooks/useProfile";

export function SettingsClient() {
  const { pick } = useLocale();
  const { agent, isLoading, ensureRunning, stop, destroy, refetch } = useAgent();
  const { update: updateProfile } = useProfile();

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
      <div className="motion-enter">
        <h1 className="text-2xl font-semibold tracking-tight">{pick({ tr: "Ayarlar", en: "Settings" })}</h1>
        <p className="text-sm text-muted-foreground">{pick({ tr: "Kişisel asistanının çalışma alanını yönet.", en: "Manage your assistant's private workspace." })}</p>
      </div>

      <CampusConnectionCard />

      <Card className="motion-enter [animation-delay:90ms]">
        <CardHeader>
          <CardTitle>{pick({ tr: "Asistan", en: "Assistant" })}</CardTitle>
          <CardDescription>{pick({ tr: "Her hesap için yalıtılmış bir çalışma alanı oluşturulur. Silme işlemi bu alandaki verileri kaldırır.", en: "Each account has an isolated workspace. Removing it also deletes its workspace data." })}</CardDescription>
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
              {agent.status === "error" && agent.error_detail ? (
                <p className="text-sm text-destructive">{agent.error_detail}</p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={ensureRunning.isPending || agent.status === "running"}
                  onClick={() => run(() => ensureRunning.mutateAsync(), "Agent started")}
                >
                  {pick({ tr: "Başlat", en: "Start" })}
                </Button>
                <Button
                  variant="outline"
                  disabled={stop.isPending || agent.status !== "running"}
                  onClick={() => run(() => stop.mutateAsync(), "Agent stopped")}
                >
                  {pick({ tr: "Durdur", en: "Stop" })}
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger render={<Button variant="destructive" />}>
                    {pick({ tr: "Sil", en: "Remove" })}
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>{pick({ tr: "Asistanın çalışma alanı silinsin mi?", en: "Remove this assistant workspace?" })}</AlertDialogTitle>
                      <AlertDialogDescription>
                        {pick({ tr: "Çalışma alanı durdurulur ve içindeki veriler silinir. Daha sonra yeniden oluşturabilirsin.", en: "This stops the workspace and deletes its data. You can create a fresh one later." })}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>{pick({ tr: "Vazgeç", en: "Cancel" })}</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => run(() => destroy.mutateAsync(), "Agent destroyed")}
                      >
                        {pick({ tr: "Çalışma alanını sil", en: "Remove workspace" })}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-muted-foreground">{pick({ tr: "Bu hesap için henüz bir asistan çalışma alanı yok.", en: "This account does not have an assistant workspace yet." })}</p>
              <Button onClick={() => run(() => ensureRunning.mutateAsync(), "Agent is ready")}>
                {pick({ tr: "Asistanı hazırla", en: "Set up assistant" })}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="motion-enter [animation-delay:150ms]">
        <CardHeader>
          <CardTitle>{pick({ tr: "Kurulum", en: "Setup" })}</CardTitle>
          <CardDescription>
            {pick({
              tr: "Tanıtım adımlarını baştan görmek istersen tekrar başlatabilirsin. Kayıtlı ayarların silinmez.",
              en: "Walk through the setup steps again if you want to revisit them. Nothing you've already saved is cleared.",
            })}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="outline"
            disabled={updateProfile.isPending}
            onClick={() =>
              run(
                () => updateProfile.mutateAsync({ onboarding_completed: false, onboarding_step: "welcome" }),
                pick({ tr: "Kurulum tekrar açıldı.", en: "Setup reopened." }),
              )
            }
          >
            {updateProfile.isPending ? <Loader2Icon className="animate-spin" /> : null}
            {pick({ tr: "Kurulumu tekrar çalıştır", en: "Run setup again" })}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
