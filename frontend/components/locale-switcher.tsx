"use client";

import { LanguagesIcon } from "lucide-react";
import { useId } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";
import { captureProductEvent } from "@/components/posthog-analytics";

export function LocaleSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useLocale();
  const instanceId = useId();
  const reduceMotion = useReducedMotion();

  return (
    <div role="group" aria-label="Dil seçimi / Language selection" className={cn("glass-control group inline-flex min-h-11 items-center gap-0.5 rounded-full p-1", className)}>
      <LanguagesIcon className="relative z-10 ml-1.5 mr-0.5 size-3.5 text-muted-foreground transition-transform duration-500 group-hover:rotate-6 group-hover:scale-105" aria-hidden />
      {(["tr", "en"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => {
            setLocale(item);
            captureProductEvent("language_changed", { locale: item });
          }}
          className={cn(
            "relative isolate min-h-9 min-w-10 overflow-hidden rounded-full px-3 py-1 text-[11px] font-bold tracking-wide uppercase outline-none transition-[color,transform] duration-300 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-transparent active:scale-95",
            locale === item
              ? "text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
          aria-pressed={locale === item}
          aria-label={item === "tr" ? "Türkçe" : "English"}
        >
          {locale === item ? (
            <motion.span
              layoutId={`locale-glass-selection-${instanceId}`}
              className="glass-selection absolute inset-0 -z-10 rounded-full"
              transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 36, mass: 0.7 }}
            />
          ) : null}
          <span className="relative z-10">{item}</span>
        </button>
      ))}
    </div>
  );
}
