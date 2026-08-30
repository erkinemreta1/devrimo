"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2Icon, Loader2Icon, LockIcon, TriangleAlertIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { CampusToolToggle } from "@/components/onboarding/campus-tool-toggle";
import { useLocale } from "@/components/locale-provider";
import { useCampus } from "@/hooks/useCampus";

/**
 * Manage the METU connection after onboarding.
 *
 * Tool toggles are staged locally and saved on an explicit click rather than
 * per-toggle, because every save rebuilds the agent container — a student
 * flipping three switches shouldn't pay for three restarts.
 */
export function CampusConnectionCard() {
  const { pick, locale } = useLocale();
  const { connection, tools, isLoading, connect, disconnect, apply } = useCampus();

  // Draft-or-server: null means "the student hasn't touched this field, show
  // what's stored". Deriving beats syncing state in an effect, which would
  // clobber typing every time the connection query refetches.
  const [usernameDraft, setUsernameDraft] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<string[] | null>(null);

  const username = usernameDraft ?? connection?.metu_username ?? "";

  const enabled = useMemo(
    () => selected ?? connection?.enabled_tools ?? [],
    [selected, connection?.enabled_tools],
  );
  const dirty =
    selected !== null &&
    JSON.stringify([...enabled].sort()) !==
      JSON.stringify([...(connection?.enabled_tools ?? [])].sort());
  const busy = connect.isPending || disconnect.isPending || apply.isPending;

  async function save() {
    if (!username.trim()) {
      toast.error(pick({ tr: "ODTÜ kullanıcı adı gerekli.", en: "A METU username is required." }));
      return;
    }
    try {
      const result = await connect.mutateAsync({
        metu_username: username.trim(),
        ...(password ? { metu_password: password } : {}),
        locale,
        enabled_tools: enabled,
      });
      setPassword("");
      setSelected(null);
      toast.success(
        result.verified_at
          ? pick({ tr: "ODTÜ bağlantın güncellendi.", en: "Your METU connection is updated." })
          : pick({
              tr: "Kaydedildi, ancak ODTÜ girişi doğrulanamadı.",
              en: "Saved, but the METU sign-in could not be verified.",
            }),
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save.");
    }
  }

  async function run(action: () => Promise<unknown>, success: string) {
    try {
      await action();
      toast.success(success);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Action failed");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{pick({ tr: "ODTÜ bağlantısı", en: "METU connection" })}</CardTitle>
        <CardDescription>
          {pick({
            tr: "Kampüs araçları ODTÜ sistemlerine senin adına giriş yapar. Şifren şifrelenerek saklanır ve yalnızca kendi çalışma alanındaki araçlara verilir.",
            en: "The campus tools sign in to METU as you. Your password is stored encrypted and handed only to the tools inside your own workspace.",
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            {pick({ tr: "Yükleniyor…", en: "Loading…" })}
          </div>
        ) : (
          <>
            {connection?.connected ? (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {connection.verified_at ? (
                  <span className="inline-flex items-center gap-1.5 text-primary">
                    <CheckCircle2Icon className="size-4" />
                    {pick({ tr: "Bağlı ve doğrulandı", en: "Connected and verified" })}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                    <TriangleAlertIcon className="size-4" />
                    {pick({ tr: "Bağlı, doğrulanmadı", en: "Connected, not verified" })}
                  </span>
                )}
                <span className="text-muted-foreground">{connection.metu_username}</span>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {pick({
                  tr: "ODTÜ hesabın bağlı değil. Kampüs araçları bağlanana kadar çalışmaz.",
                  en: "Your METU account isn't connected. The campus tools won't run until it is.",
                })}
              </p>
            )}

            {connection?.verification_error ? (
              <p className="text-xs text-muted-foreground">{connection.verification_error}</p>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-2">
                <Label htmlFor="settings-metu-username">
                  {pick({ tr: "ODTÜ kullanıcı adı", en: "METU username" })}
                </Label>
                <Input
                  id="settings-metu-username"
                  value={username}
                  spellCheck={false}
                  autoComplete="username"
                  placeholder="e123456"
                  onChange={(event) => setUsernameDraft(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="settings-metu-password">
                  {pick({ tr: "ODTÜ şifresi", en: "METU password" })}
                </Label>
                <Input
                  id="settings-metu-password"
                  type="password"
                  value={password}
                  autoComplete="current-password"
                  placeholder={
                    connection?.has_password
                      ? pick({ tr: "Kayıtlı — değiştirmek için yaz", en: "Stored — type to replace" })
                      : "••••••••"
                  }
                  onChange={(event) => setPassword(event.target.value)}
                />
              </div>
            </div>

            <div className="flex flex-col gap-2.5">
              <p className="text-sm font-medium">{pick({ tr: "Kampüs araçları", en: "Campus tools" })}</p>
              {tools.map((tool) => (
                <CampusToolToggle
                  key={tool.id}
                  tool={tool}
                  checked={enabled.includes(tool.id)}
                  disabled={busy}
                  onChange={(next) =>
                    setSelected(next ? [...enabled, tool.id] : enabled.filter((id) => id !== tool.id))
                  }
                />
              ))}
            </div>

            {connection?.needs_restart ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-500/10 p-3">
                <p className="text-xs leading-5 text-amber-700 dark:text-amber-400">
                  {pick({
                    tr: "Değişiklikler asistanına henüz uygulanmadı.",
                    en: "These changes aren't live in your assistant yet.",
                  })}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => apply.mutateAsync(),
                      pick({ tr: "Asistanın güncellendi.", en: "Your assistant is updated." }),
                    )
                  }
                >
                  {apply.isPending ? <Loader2Icon className="animate-spin" /> : null}
                  {pick({ tr: "Şimdi uygula", en: "Apply now" })}
                </Button>
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button
                disabled={busy || (!password && !dirty && Boolean(connection?.connected))}
                onClick={() => void save()}
              >
                {connect.isPending ? <Loader2Icon className="animate-spin" /> : null}
                {connection?.connected
                  ? pick({ tr: "Değişiklikleri kaydet", en: "Save changes" })
                  : pick({ tr: "Bağlan", en: "Connect" })}
              </Button>

              {connection?.connected ? (
                <AlertDialog>
                  <AlertDialogTrigger render={<Button variant="outline" disabled={busy} />}>
                    {pick({ tr: "Bağlantıyı kaldır", en: "Disconnect" })}
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        {pick({ tr: "ODTÜ bağlantısı kaldırılsın mı?", en: "Disconnect your METU account?" })}
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        {pick({
                          tr: "Kayıtlı ODTÜ şifren silinir ve kampüs araçları asistanından kaldırılır. Sohbet geçmişin durur.",
                          en: "Your stored METU password is deleted and the campus tools are removed from your assistant. Your chat history stays.",
                        })}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>{pick({ tr: "Vazgeç", en: "Cancel" })}</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() =>
                          run(
                            async () => {
                              await disconnect.mutateAsync();
                              setSelected(null);
                              setUsernameDraft(null);
                              setPassword("");
                            },
                            pick({ tr: "ODTÜ bağlantın kaldırıldı.", en: "Your METU account is disconnected." }),
                          )
                        }
                      >
                        {pick({ tr: "Bağlantıyı kaldır", en: "Disconnect" })}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : null}
            </div>

            <p className="flex items-start gap-2 text-[11px] leading-4 text-muted-foreground">
              <LockIcon className="mt-0.5 size-3.5 shrink-0" />
              <span>
                {pick({
                  tr: "Şifren bu arayüze bir daha hiçbir zaman geri gönderilmez ve asistanın sohbet geçmişine yazılmaz.",
                  en: "Your password is never sent back to this interface and never written into the assistant's chat history.",
                })}
              </span>
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
