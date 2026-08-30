"use client";

import { unstable_useComposerInput } from "@assistant-ui/react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/components/locale-provider";

const prompts = {
  tr: [
    "Bu dönem ekle-bırak son günü ne zaman?",
    "Bu hafta için ders çalışma planı hazırla",
    "Bu akşam kampüste nerede çalışabilirim?",
    "Bu haftaki ODTÜClass duyurularını özetle",
  ],
  en: [
    "When is the add-drop deadline this semester?",
    "Build me a study plan for this week",
    "Where can I study on campus tonight?",
    "Summarize this week's ODTÜClass announcements",
  ],
};

export function MetuWelcome() {
  const { pick } = useLocale();
  return (
    <div className="relative mb-8 flex flex-col items-center px-4 text-center">
      <h1 className="motion-enter text-2xl font-semibold tracking-tight sm:text-3xl">
        {pick({ tr: "Bugün neyi birlikte çözelim?", en: "What can we solve today?" })}
      </h1>
      <p className="motion-enter mt-2 max-w-md text-sm text-muted-foreground [animation-delay:70ms]">
        {pick({
          tr: "Dersler, akademik takvim, kütüphane ve kampüs yaşamı için bağlamını bilen kişisel asistanın.",
          en: "Your context-aware assistant for courses, the academic calendar, library resources, and campus life.",
        })}
      </p>
    </div>
  );
}

export function MetuStarterPrompts() {
  const { setText, send, isDisabled } = unstable_useComposerInput();
  const { locale } = useLocale();

  return (
    <div className="flex w-full flex-wrap items-center justify-center gap-2 px-1 pb-1">
      {prompts[locale].map((prompt, index) => (
        <Button
          key={prompt}
          type="button"
          variant="outline"
          disabled={isDisabled}
          className="motion-enter h-auto max-w-full rounded-full bg-gradient-to-b from-card to-background px-3.5 py-1.5 text-left text-sm font-normal whitespace-normal shadow-sm transition-[transform,background-color,border-color,box-shadow] duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[0_8px_24px_rgb(227_24_55/10%)]"
          style={{ animationDelay: `${220 + index * 55}ms` }}
          onClick={() => { setText(prompt); send(); }}
        >
          {prompt}
        </Button>
      ))}
    </div>
  );
}
