"use client";

import { useState } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckCircle2Icon,
  Loader2Icon,
  LockIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLocale } from "@/components/locale-provider";
import { useCampus } from "@/hooks/useCampus";
import { useProfile } from "@/hooks/useProfile";
import { CampusToolToggle } from "@/components/onboarding/campus-tool-toggle";
import { StepIndicator } from "@/components/onboarding/step-indicator";
import { ONBOARDING_STEPS, stepIndex, type OnboardingStep } from "@/components/onboarding/steps";
import type { CampusTool } from "@/lib/types";

const STARTER_PROMPTS = {
  tr: [
    "Bu dönem ekle-bırak son günü ne zaman?",
    "Bu haftaki ODTÜClass duyurularını özetle",
    "Transkriptimden genel ortalamamı çıkar",
    "Yaklaşan ödev teslimlerimi listele",
  ],
  en: [
    "When is the add-drop deadline this semester?",
    "Summarize this week's ODTÜClass announcements",
    "What is my CGPA from my transcript?",
    "List my upcoming assignment deadlines",
  ],
};

/**
 * The first-run wizard.
 *
 * Progress is written to the profile after each step rather than only at the
 * end, so closing the tab halfway through resumes here instead of starting
 * over. The METU password is held in component state and sent exactly once,
 * on the connect step — it is never written to the profile, to localStorage,
 * or back into any field after submission.
 */
export function OnboardingFlow({ onDone }: { onDone?: () => void }) {
  const { pick, locale, setLocale } = useLocale();
  const { profile, update } = useProfile();
  const { connection, tools, connect, isLoading: campusLoading } = useCampus();

  // Every field below is draft-or-server: `null` means the student hasn't
  // touched it, so the stored value shows through. Derived rather than synced
  // in an effect, which would overwrite whatever they were typing on each
  // background refetch of the profile or connection.
  const [stepOverride, setStepOverride] = useState<OnboardingStep | null>(null);
  const [displayNameDraft, setDisplayNameDraft] = useState<string | null>(null);
  const [usernameDraft, setUsernameDraft] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [selected, setSelected] = useState<string[] | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  // Resuming where the student left off falls out of this for free: the
  // stored step is the starting point until they navigate.
  const step = stepOverride ?? ONBOARDING_STEPS[stepIndex(profile?.onboarding_step)];
  const displayName = displayNameDraft ?? profile?.display_name ?? "";
  const username = usernameDraft ?? connection?.metu_username ?? "";

  // Not manually memoized: the React Compiler does it, and a hand-written
  // dependency list here reads `connection?.enabled_tools` where the compiler
  // infers `connection`, which makes it bail out of optimizing the component.
  const defaultSelection = connection?.enabled_tools?.length
    ? connection.enabled_tools
    : tools.filter((tool: CampusTool) => tool.default_enabled).map((tool) => tool.id);
  const enabledTools = selected ?? defaultSelection;

  const index = ONBOARDING_STEPS.indexOf(step);
  const busy = connect.isPending || update.isPending;

  function goTo(next: OnboardingStep) {
    setFormError(null);
    setStepOverride(next);
    // Fire-and-forget: losing a step marker is not worth blocking the UI on,
    // and the next write will correct it.
    update.mutate({ onboarding_step: next });
  }

  async function submitConnection(skipVerification = false) {
    setFormError(null);
    setWarning(null);

    if (!username.trim()) {
      setFormError(pick({ tr: "ODTÜ kullanıcı adını gir.", en: "Enter your METU username." }));
      return;
    }
    if (!password && !connection?.has_password) {
      setFormError(pick({ tr: "ODTÜ şifreni gir.", en: "Enter your METU password." }));
      return;
    }

    try {
      const result = await connect.mutateAsync({
        metu_username: username.trim(),
        ...(password ? { metu_password: password } : {}),
        locale,
        enabled_tools: enabledTools,
        skip_verification: skipVerification,
      });
      // Never keep the password around after it has been stored.
      setPassword("");
      if (!result.verified_at && result.verification_error) {
        setWarning(result.verification_error);
      }
      goTo("tools");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save your METU connection.");
    }
  }

  async function saveToolSelection() {
    setFormError(null);
    if (!connection?.connected) {
      goTo("ready");
      return;
    }
    try {
      await connect.mutateAsync({
        metu_username: username.trim() || connection.metu_username || "",
        locale,
        enabled_tools: enabledTools,
      });
      goTo("ready");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not save your tool selection.");
    }
  }

  async function finish() {
    setFormError(null);
    try {
      await update.mutateAsync({
        display_name: displayName.trim() || null,
        locale,
        onboarding_step: "ready",
        onboarding_completed: true,
      });
      onDone?.();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Could not finish setup.");
    }
  }

  async function skipSetup() {
    await update.mutateAsync({ onboarding_completed: true, onboarding_step: "ready" });
    onDone?.();
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-xl flex-col overflow-y-auto px-5 py-8">
      <div className="mb-7 flex flex-col items-center gap-4">
        <BrandMark className="size-11 text-sm" />
        <StepIndicator current={index} />
      </div>

      {step === "welcome" ? (
        <section className="flex flex-1 flex-col">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            {pick({ tr: "Devrimo'ya hoş geldin", en: "Welcome to Devrimo" })}
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {pick({
              tr: "Devrimo, ODTÜ kampüs hayatı için kişisel bir asistan. Sadece sana ait, yalıtılmış bir çalışma alanında çalışır — ne konuştuğunuz başka hiçbir öğrenciyle paylaşılmaz.",
              en: "Devrimo is a personal assistant for METU campus life. It runs in an isolated workspace that belongs only to you — nothing you say here is shared with another student.",
            })}
          </p>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            {pick({
              tr: "Sırada ODTÜ hesabını bağlamak var. Bu, asistanın ders programın, transkriptin, ODTÜClass duyuruların ve e-postan gibi sana özel bilgilere ulaşmasını sağlar.",
              en: "Next you'll connect your METU account. That's what lets the assistant reach your own schedule, transcript, ODTÜClass announcements, and mail.",
            })}
          </p>

          <div className="mt-6 flex flex-col gap-2">
            <Label htmlFor="display-name">
              {pick({ tr: "Sana nasıl hitap edelim? (isteğe bağlı)", en: "What should we call you? (optional)" })}
            </Label>
            <Input
              id="display-name"
              value={displayName}
              autoComplete="given-name"
              placeholder={pick({ tr: "Deniz", en: "Deniz" })}
              onChange={(event) => setDisplayNameDraft(event.target.value)}
            />
          </div>

          <div className="mt-5 flex flex-col gap-2">
            <Label>{pick({ tr: "Dil", en: "Language" })}</Label>
            <div className="flex gap-2">
              {(["tr", "en"] as const).map((option) => (
                <Button
                  key={option}
                  type="button"
                  variant={locale === option ? "default" : "outline"}
                  size="sm"
                  onClick={() => setLocale(option)}
                >
                  {option === "tr" ? "Türkçe" : "English"}
                </Button>
              ))}
            </div>
          </div>

          <Footer
            onNext={() => goTo("connect")}
            nextLabel={pick({ tr: "Devam et", en: "Continue" })}
            onSkip={skipSetup}
            skipLabel={pick({ tr: "Şimdilik geç", en: "Skip for now" })}
            busy={busy}
          />
        </section>
      ) : null}

      {step === "connect" ? (
        <section className="flex flex-1 flex-col">
          <h1 className="text-2xl font-semibold tracking-tight">
            {pick({ tr: "ODTÜ hesabını bağla", en: "Connect your METU account" })}
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {pick({
              tr: "Kampüs araçları ODTÜ sistemlerine senin adına giriş yapar, bu yüzden ODTÜ kullanıcı adın ve şifren gerekiyor.",
              en: "The campus tools sign in to METU systems as you, so they need your METU username and password.",
            })}
          </p>

          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-border bg-muted/40 p-3.5">
            <LockIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div className="text-xs leading-5 text-muted-foreground">
              <p>
                {pick({
                  tr: "Şifren şifrelenerek saklanır ve yalnızca sana ait çalışma alanının içindeki kampüs araçlarına verilir. Arayüze bir daha asla geri gönderilmez, asistanın sohbet geçmişine yazılmaz.",
                  en: "Your password is stored encrypted and handed only to the campus tools inside your own workspace. It is never sent back to this interface and never written into the assistant's chat history.",
                })}
              </p>
              <p className="mt-2">
                {pick({
                  tr: "İstediğin zaman Ayarlar'dan bağlantıyı kaldırabilirsin; şifren silinir.",
                  en: "You can disconnect at any time from Settings, which deletes the stored password.",
                })}
              </p>
            </div>
          </div>

          <form
            className="mt-5 flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submitConnection();
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="metu-username">{pick({ tr: "ODTÜ kullanıcı adı", en: "METU username" })}</Label>
              <Input
                id="metu-username"
                value={username}
                required
                autoComplete="username"
                spellCheck={false}
                placeholder="e123456"
                onChange={(event) => setUsernameDraft(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="metu-password">{pick({ tr: "ODTÜ şifresi", en: "METU password" })}</Label>
              <Input
                id="metu-password"
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

            {formError ? (
              <p className="flex items-start gap-2 text-sm text-destructive">
                <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
                <span className="min-w-0 break-words">{formError}</span>
              </p>
            ) : null}

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => goTo("welcome")} disabled={busy}>
                <ArrowLeftIcon /> {pick({ tr: "Geri", en: "Back" })}
              </Button>
              <div className="flex items-center gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={() => goTo("tools")} disabled={busy}>
                  {pick({ tr: "Şimdilik geç", en: "Skip for now" })}
                </Button>
                <Button type="submit" disabled={busy}>
                  {connect.isPending ? <Loader2Icon className="animate-spin" /> : null}
                  {pick({ tr: "Bağlan", en: "Connect" })}
                </Button>
              </div>
            </div>
          </form>
        </section>
      ) : null}

      {step === "tools" ? (
        <section className="flex flex-1 flex-col">
          <h1 className="text-2xl font-semibold tracking-tight">
            {pick({ tr: "Kampüs araçlarını seç", en: "Choose your campus tools" })}
          </h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {pick({
              tr: "Asistanın hangi ODTÜ sistemlerine ulaşabileceğine sen karar veriyorsun. Bunları sonradan Ayarlar'dan değiştirebilirsin.",
              en: "You decide which METU systems the assistant can reach. You can change these later in Settings.",
            })}
          </p>

          {warning ? (
            <p className="mt-4 flex items-start gap-2 rounded-xl bg-amber-500/10 p-3 text-xs leading-5 text-amber-700 dark:text-amber-400">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
              <span className="min-w-0 break-words">{warning}</span>
            </p>
          ) : null}

          {!connection?.connected ? (
            <p className="mt-4 rounded-xl bg-muted/50 p-3 text-xs leading-5 text-muted-foreground">
              {pick({
                tr: "ODTÜ hesabını bağlamadın, bu yüzden bu araçlar şimdilik çalışmaz. Seçimin kaydedilir; hesabını Ayarlar'dan bağladığında devreye girerler.",
                en: "You haven't connected your METU account, so these tools won't run yet. Your choice is saved and they'll switch on once you connect from Settings.",
              })}
            </p>
          ) : null}

          <div className="mt-5 flex flex-col gap-2.5">
            {campusLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2Icon className="size-4 animate-spin" />
                {pick({ tr: "Araçlar yükleniyor…", en: "Loading tools…" })}
              </div>
            ) : (
              tools.map((tool) => (
                <CampusToolToggle
                  key={tool.id}
                  tool={tool}
                  checked={enabledTools.includes(tool.id)}
                  disabled={busy}
                  onChange={(next) =>
                    setSelected(
                      next
                        ? [...enabledTools, tool.id]
                        : enabledTools.filter((id) => id !== tool.id),
                    )
                  }
                />
              ))
            )}
          </div>

          {formError ? <p className="mt-3 text-sm text-destructive">{formError}</p> : null}

          <div className="mt-6 flex items-center justify-between gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => goTo("connect")} disabled={busy}>
              <ArrowLeftIcon /> {pick({ tr: "Geri", en: "Back" })}
            </Button>
            <Button type="button" onClick={() => void saveToolSelection()} disabled={busy}>
              {connect.isPending ? <Loader2Icon className="animate-spin" /> : null}
              {pick({ tr: "Devam et", en: "Continue" })} <ArrowRightIcon />
            </Button>
          </div>
        </section>
      ) : null}

      {step === "ready" ? (
        <section className="flex flex-1 flex-col">
          <div className="flex items-center gap-2 text-primary">
            <CheckCircle2Icon className="size-5" />
            <span className="text-xs font-semibold tracking-[0.18em] uppercase">
              {pick({ tr: "Hazırsın", en: "All set" })}
            </span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {displayName.trim()
              ? pick({ tr: `Hadi başlayalım, ${displayName.trim()}`, en: `Let's get started, ${displayName.trim()}` })
              : pick({ tr: "Hadi başlayalım", en: "Let's get started" })}
          </h1>

          <ActiveToolSummary tools={tools} enabled={enabledTools} connected={Boolean(connection?.connected)} />

          <p className="mt-6 text-sm font-medium">{pick({ tr: "Şunları deneyebilirsin:", en: "Try asking:" })}</p>
          <ul className="mt-2 flex flex-col gap-1.5">
            {STARTER_PROMPTS[locale].map((prompt) => (
              <li key={prompt} className="rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                {prompt}
              </li>
            ))}
          </ul>

          {formError ? <p className="mt-3 text-sm text-destructive">{formError}</p> : null}

          <div className="mt-6 flex items-center justify-between gap-3">
            <Button type="button" variant="ghost" size="sm" onClick={() => goTo("tools")} disabled={busy}>
              <ArrowLeftIcon /> {pick({ tr: "Geri", en: "Back" })}
            </Button>
            <Button type="button" onClick={() => void finish()} disabled={busy}>
              {update.isPending ? <Loader2Icon className="animate-spin" /> : null}
              {pick({ tr: "Sohbete başla", en: "Start chatting" })}
            </Button>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ActiveToolSummary({
  tools,
  enabled,
  connected,
}: {
  tools: CampusTool[];
  enabled: string[];
  connected: boolean;
}) {
  const { pick, locale } = useLocale();
  const active = tools.filter((tool) => enabled.includes(tool.id));

  if (!connected || active.length === 0) {
    return (
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        {pick({
          tr: "Asistanın genel bilgisiyle çalışmaya hazır. Kampüs araçlarını istediğin zaman Ayarlar'dan açabilirsin.",
          en: "Your assistant is ready to work from general knowledge. You can switch the campus tools on any time from Settings.",
        })}
      </p>
    );
  }

  return (
    <>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">
        {pick({
          tr: "Asistanın artık şu ODTÜ sistemlerine ulaşabiliyor:",
          en: "Your assistant can now reach these METU systems:",
        })}
      </p>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {active.map((tool) => (
          <li
            key={tool.id}
            className="rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-medium text-foreground"
          >
            {locale === "tr" ? tool.name_tr : tool.name_en}
          </li>
        ))}
      </ul>
    </>
  );
}

function Footer({
  onNext,
  nextLabel,
  onSkip,
  skipLabel,
  busy,
}: {
  onNext: () => void;
  nextLabel: string;
  onSkip: () => void;
  skipLabel: string;
  busy: boolean;
}) {
  return (
    <div className="mt-7 flex items-center justify-between gap-3">
      <Button type="button" variant="ghost" size="sm" onClick={onSkip} disabled={busy}>
        {skipLabel}
      </Button>
      <Button type="button" onClick={onNext} disabled={busy}>
        {nextLabel} <ArrowRightIcon />
      </Button>
    </div>
  );
}
