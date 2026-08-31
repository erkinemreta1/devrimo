"use client";

import { unstable_useComposerInput } from "@assistant-ui/react";
import {
  BookOpenCheckIcon,
  CalendarDaysIcon,
  LibraryIcon,
  RouteIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useLocale } from "@/components/locale-provider";

const suggestions = {
  tr: [
    { label: "Haftalık plan", prompt: "Programımdaki boşluklara göre bu hafta için gerçekçi bir çalışma planı yap", icon: CalendarDaysIcon },
    { label: "Akademik takvim", prompt: "Bu dönem yaklaşan önemli akademik tarihleri sırala", icon: BookOpenCheckIcon },
    { label: "Ders seçimi", prompt: "CENG 334 için ön koşulları ve açılan şubeleri karşılaştır", icon: LibraryIcon },
    { label: "Kampüs yaşamı", prompt: "Bu akşam sessiz çalışabileceğim kampüs seçeneklerini öner", icon: RouteIcon },
  ],
  en: [
    { label: "Weekly plan", prompt: "Build a realistic study plan around the gaps in my schedule this week", icon: CalendarDaysIcon },
    { label: "Academic calendar", prompt: "List the important academic dates coming up this semester", icon: BookOpenCheckIcon },
    { label: "Course planning", prompt: "Compare the prerequisites and available sections for CENG 334", icon: LibraryIcon },
    { label: "Campus life", prompt: "Suggest quiet places on campus where I can study tonight", icon: RouteIcon },
  ],
};

export function MetuWelcome() {
  const { pick } = useLocale();
  return (
    <div className="relative mx-auto mb-7 flex max-w-2xl flex-col items-center px-4 text-center">
      <div className="motion-enter mb-4 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/[0.045] px-3 py-1.5 text-xs font-medium text-primary">
        <ShieldCheckIcon className="size-3.5" />
        {pick({ tr: "Kişisel, kontrollü ve sana özel", en: "Personal, controlled, and private to you" })}
      </div>
      <h1 className="motion-enter text-3xl font-semibold tracking-[-0.045em] sm:text-4xl [animation-delay:45ms]">
        {pick({ tr: "Bugün neyi kolaylaştıralım?", en: "What should we make easier today?" })}
      </h1>
      <p className="motion-enter mt-3 max-w-xl text-sm leading-6 text-muted-foreground [animation-delay:90ms]">
        {pick({
          tr: "Ders planlama, akademik tarihler ve kampüs yaşamı için yardım al. ODTÜClass ve e-posta bilgileri yalnızca Ayarlar'da izin verdiğinde kullanılır.",
          en: "Get help with course planning, academic dates, and campus life. ODTÜClass and email information are used only when you allow them in Settings.",
        })}
      </p>
    </div>
  );
}

export function MetuStarterPrompts() {
  const { setText, send, isDisabled } = unstable_useComposerInput();
  const { locale, pick } = useLocale();

  return (
    <section aria-label={pick({ tr: "Örnek sorular", en: "Example questions" })} className="w-full pb-1">
      <p className="mb-2 px-1 text-xs font-medium text-muted-foreground">{pick({ tr: "Bir örnekle başla", en: "Start with an example" })}</p>
      <div className="grid w-full gap-2 sm:grid-cols-2">
        {suggestions[locale].map(({ label, prompt, icon: Icon }, index) => (
          <button
            key={prompt}
            type="button"
            disabled={isDisabled}
            className="motion-enter group flex min-h-[4.5rem] items-start gap-3 rounded-xl border border-border/70 bg-card/80 p-3 text-left shadow-[0_8px_26px_rgb(70_48_35/5%)] transition-[transform,border-color,background-color,box-shadow] hover:-translate-y-0.5 hover:border-primary/25 hover:bg-card hover:shadow-[0_12px_30px_rgb(215_24_63/8%)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
            style={{ animationDelay: `${180 + index * 45}ms` }}
            onClick={() => { setText(prompt); send(); }}
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary"><Icon className="size-4" /></span>
            <span className="min-w-0">
              <span className="block text-[11px] font-semibold tracking-[0.08em] text-primary uppercase">{label}</span>
              <span className="mt-1 block text-sm leading-5 text-foreground/90">{prompt}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
