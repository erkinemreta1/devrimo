"use client";

import { unstable_useComposerInput } from "@assistant-ui/react";
import { BrandMark } from "@/components/brand-mark";
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
    <div className="mb-8 flex flex-col items-center px-4 text-center">
      <BrandMark className="mb-4 size-11 text-sm" />
      <p className="text-xs font-medium tracking-[0.18em] text-primary uppercase">
        {pick({ tr: "ODTÜ öğrencileri için", en: "Built for METU students" })}
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
        {pick({ tr: "Bugün neyi birlikte çözelim?", en: "What can we solve today?" })}
      </h1>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
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
      {prompts[locale].map((prompt) => (
        <Button
          key={prompt}
          type="button"
          variant="outline"
          disabled={isDisabled}
          className="h-auto max-w-full rounded-full px-3.5 py-1.5 text-left text-sm font-normal whitespace-normal"
          onClick={() => { setText(prompt); send(); }}
        >
          {prompt}
        </Button>
      ))}
    </div>
  );
}
