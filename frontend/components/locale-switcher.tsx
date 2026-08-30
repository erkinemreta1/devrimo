"use client";

import { LanguagesIcon } from "lucide-react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";

export function LocaleSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useLocale();

  return (
    <div role="group" aria-label="Dil seçimi / Language selection" className={cn("group inline-flex min-h-11 items-center gap-1 rounded-full border bg-card/80 p-1 shadow-sm backdrop-blur", className)}>
      <LanguagesIcon className="ml-1.5 size-3.5 text-muted-foreground transition-transform duration-300 group-hover:rotate-6" aria-hidden />
      {(["tr", "en"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setLocale(item)}
          className={cn(
            "min-h-9 rounded-full px-3 py-1 text-[11px] font-bold tracking-wide transition-[color,background-color,transform,box-shadow] duration-200 uppercase outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-90",
            locale === item
              ? "motion-pop scale-105 bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:-translate-y-px hover:bg-muted hover:text-foreground",
          )}
          aria-pressed={locale === item}
          aria-label={item === "tr" ? "Türkçe" : "English"}
        >
          {item}
        </button>
      ))}
    </div>
  );
}
