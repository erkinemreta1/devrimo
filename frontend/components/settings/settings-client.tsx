"use client";

import { useEffect } from "react";
import { toast } from "sonner";
import {
  BrainIcon,
  CableIcon,
  ChevronRightIcon,
  Loader2Icon,
  RotateCcwIcon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
  SparklesIcon,
  Trash2Icon,
} from "lucide-react";
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
import { useMemories } from "@/hooks/useMemories";
import { captureError, captureProductEvent } from "@/components/posthog-analytics";

export function SettingsClient() {
  const { pick } = useLocale();
  const { update: updateProfile } = useProfile();
  const { memories, isLoading: memoriesLoading, clear: clearMemories } = useMemories();

  useEffect(() => {
    captureProductEvent("settings_opened", {});
  }, []);

  async function clearAllMemories() {
    try {
      await clearMemories.mutateAsync();
      toast.success(pick({ tr: "Hatırlanan tercihlerin silindi.", en: "Remembered preferences cleared." }));
    } catch (error) {
      captureError(error, { source: "settings_clear_memories" });
      toast.error(error instanceof Error ? error.message : pick({ tr: "Tercihler silinemedi.", en: "Preferences could not be cleared." }));
    }
  }

  async function reopenSetup() {
    try {
      await updateProfile.mutateAsync({ onboarding_completed: false, onboarding_step: "welcome" });
      toast.success(pick({ tr: "Kurulum adımları tekrar açıldı.", en: "Setup steps reopened." }));
    } catch (error) {
      captureError(error, { source: "settings_reopen_setup" });
      toast.error(error instanceof Error ? error.message : pick({ tr: "Kurulum açılamadı.", en: "Setup could not be reopened." }));
    }
  }

  const navigation = [
    { href: "#connection", icon: CableIcon, label: pick({ tr: "ODTÜ bağlantısı", en: "METU connection" }) },
    { href: "#privacy", icon: ShieldCheckIcon, label: pick({ tr: "Veri erişimi", en: "Data access" }) },
    { href: "#memory", icon: BrainIcon, label: pick({ tr: "Hatırlananlar", en: "Remembered items" }) },
    { href: "#setup", icon: RotateCcwIcon, label: pick({ tr: "Kurulum", en: "Setup" }) },
  ];

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-7 lg:px-8">
      <header className="motion-enter relative overflow-hidden rounded-3xl border bg-card/85 p-5 shadow-sm sm:p-7">
        <div className="absolute -right-12 -top-20 size-52 rounded-full bg-primary/8 blur-2xl" aria-hidden />
        <div className="relative flex max-w-3xl items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-[0_7px_0_#901129]"><SlidersHorizontalIcon className="size-5" /></span>
          <div>
            <Badge variant="outline" className="mb-3 border-primary/20 bg-primary/5 text-primary">{pick({ tr: "Kontrol sende", en: "You're in control" })}</Badge>
            <h1 className="text-2xl font-semibold tracking-[-0.035em] sm:text-3xl">{pick({ tr: "Ayarlar ve gizlilik", en: "Settings and privacy" })}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{pick({ tr: "ODTÜ bağlantını, hangi bilgi kaynaklarının kullanılabileceğini ve asistanın hatırladıklarını tek yerde yönet.", en: "Manage your METU connection, which information sources may be used, and what the assistant remembers—all in one place." })}</p>
          </div>
        </div>
      </header>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <aside className="hidden lg:sticky lg:top-6 lg:block">
          <nav aria-label={pick({ tr: "Ayar bölümleri", en: "Settings sections" })} className="rounded-2xl border bg-card/70 p-2 shadow-sm">
            {navigation.map(({ href, icon: Icon, label }) => (
              <a key={href} href={href} className="group flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                <Icon className="size-4 text-primary" />
                <span className="flex-1">{label}</span>
                <ChevronRightIcon className="size-3.5 opacity-0 transition-opacity group-hover:opacity-60" />
              </a>
            ))}
          </nav>
          <div className="mt-3 rounded-2xl border border-primary/15 bg-primary/[0.035] p-4">
            <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheckIcon className="size-4 text-primary" />{pick({ tr: "Gizlilik özeti", en: "Privacy summary" })}</div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{pick({ tr: "E-posta ve ODTÜClass isteğe bağlıdır. Şifren gösterilmez; içerikler yönetici ekranlarına taşınmaz.", en: "Email and ODTÜClass are optional. Your password is never shown, and contents never appear in admin views." })}</p>
          </div>
        </aside>

        <main className="min-w-0 space-y-5">
          <CampusConnectionCard />

          <Card id="memory" className="motion-enter surface-raised scroll-mt-24 border-0 ring-1 ring-foreground/8 [animation-delay:70ms]">
            <CardHeader className="border-b bg-muted/20">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><BrainIcon className="size-4" /></span>
                  <div><CardTitle>{pick({ tr: "Hatırlanan tercihler", en: "Remembered preferences" })}</CardTitle><CardDescription className="mt-1">{pick({ tr: "Yalnızca açıkça hatırlamasını istediğin, hassas olmayan tercihler burada tutulur.", en: "Only non-sensitive preferences you explicitly asked the assistant to remember are kept here." })}</CardDescription></div>
                </div>
                {!memoriesLoading ? <Badge variant="secondary">{memories.length} {pick({ tr: "kayıt", en: memories.length === 1 ? "item" : "items" })}</Badge> : null}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {memoriesLoading ? (
                <div className="flex min-h-28 items-center justify-center gap-2 text-sm text-muted-foreground"><Loader2Icon className="size-4 animate-spin" />{pick({ tr: "Hatırlananlar yükleniyor…", en: "Loading remembered items…" })}</div>
              ) : memories.length ? (
                <ul className="grid gap-2 sm:grid-cols-2">
                  {memories.map((memory) => <li key={memory.id} className="rounded-xl border bg-background/55 px-4 py-3 text-sm leading-5">{memory.content}</li>)}
                </ul>
              ) : (
                <div className="flex min-h-28 flex-col items-center justify-center rounded-xl border border-dashed bg-muted/15 px-4 text-center">
                  <SparklesIcon className="size-5 text-primary" />
                  <p className="mt-2 text-sm font-medium">{pick({ tr: "Henüz hatırlanan bir tercih yok", en: "Nothing is remembered yet" })}</p>
                  <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{pick({ tr: "Örneğin “Yanıtları kısa tut” dediğinde ve hatırlamasını istediğinde burada görünür.", en: "For example, an instruction such as “Keep answers concise” appears here when you ask it to remember." })}</p>
                </div>
              )}

              {memories.length ? (
                <AlertDialog>
                  <AlertDialogTrigger render={<Button variant="outline" className="text-destructive" />}><Trash2Icon />{pick({ tr: "Tümünü unuttur", en: "Forget everything" })}</AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader><AlertDialogTitle>{pick({ tr: "Tüm tercihler unutulsun mu?", en: "Forget all preferences?" })}</AlertDialogTitle><AlertDialogDescription>{pick({ tr: "Hatırlanan tercihler kalıcı olarak silinir. Sohbet geçmişin ve ODTÜ bağlantın değişmez.", en: "Remembered preferences are permanently deleted. Chat history and your METU connection are unchanged." })}</AlertDialogDescription></AlertDialogHeader>
                    <AlertDialogFooter><AlertDialogCancel>{pick({ tr: "Vazgeç", en: "Cancel" })}</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={clearMemories.isPending} onClick={() => void clearAllMemories()}>{clearMemories.isPending ? <Loader2Icon className="animate-spin" /> : <Trash2Icon />}{pick({ tr: "Tümünü unuttur", en: "Forget everything" })}</AlertDialogAction></AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : null}
            </CardContent>
          </Card>

          <Card id="setup" className="motion-enter surface-raised scroll-mt-24 border-0 ring-1 ring-foreground/8 [animation-delay:110ms]">
            <CardHeader className="border-b bg-muted/20">
              <div className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-muted text-muted-foreground"><RotateCcwIcon className="size-4" /></span><div><CardTitle>{pick({ tr: "Kurulumu yeniden gözden geçir", en: "Review setup again" })}</CardTitle><CardDescription className="mt-1">{pick({ tr: "Dil, hitap şekli, ODTÜ bağlantısı ve veri erişimi seçimlerini adım adım yeniden incele. Mevcut kayıtların silinmez.", en: "Review language, how you're addressed, your METU connection, and data-access choices step by step. Existing data is not deleted." })}</CardDescription></div></div>
            </CardHeader>
            <CardContent>
              <Button variant="outline" disabled={updateProfile.isPending} onClick={() => void reopenSetup()}>{updateProfile.isPending ? <Loader2Icon className="animate-spin" /> : <RotateCcwIcon />}{pick({ tr: "Kurulum adımlarını aç", en: "Open setup steps" })}</Button>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  );
}
