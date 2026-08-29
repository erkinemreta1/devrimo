"use client";

import { LanguagesIcon } from "lucide-react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";

export function LocaleSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useLocale();

  return (
    <div className={cn("inline-flex items-center gap-1 rounded-full border bg-card/80 p-1 shadow-sm backdrop-blur", className)}>
      <LanguagesIcon className="ml-1.5 size-3.5 text-muted-foreground" aria-hidden />
      {(["tr", "en"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setLocale(item)}
          className={cn(
            "rounded-full px-2.5 py-1 text-[11px] font-bold tracking-wide transition-colors uppercase",
            locale === item ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
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
