"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";
import { captureProductEvent } from "@/components/posthog-analytics";

export function ThemeSwitcher({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const { pick } = useLocale();
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const activeTheme = mounted ? (theme ?? "light") : "light";

  return (
    <div
      className={cn("inline-flex h-11 items-center rounded-xl border border-border bg-background/85 p-1 shadow-sm", className)}
      role="group"
      aria-label={pick({ tr: "Renk teması", en: "Color theme" })}
    >
      {([
        { value: "light", icon: SunIcon, tr: "Açık tema", en: "Light theme" },
        { value: "dark", icon: MoonIcon, tr: "Koyu tema", en: "Dark theme" },
      ] as const).map(({ value, icon: Icon, tr, en }) => {
        const active = activeTheme === value;
        return (
          <button
            key={value}
            type="button"
            aria-label={pick({ tr, en })}
            aria-pressed={active}
            onClick={() => {
              setTheme(value);
              captureProductEvent("theme_changed", { theme: value });
            }}
            className={cn(
              "group grid size-9 place-items-center rounded-lg text-muted-foreground transition-[color,background-color,transform,box-shadow] duration-200 outline-none",
              "hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              "hover:-translate-y-px active:scale-90",
              active && "bg-foreground text-background shadow-sm hover:bg-foreground hover:text-background hover:translate-y-0",
            )}
          >
            <Icon
              className={cn(
                "size-3.5 transition-[transform,opacity] duration-300",
                active
                  ? value === "light"
                    ? "motion-pop rotate-90 scale-110 opacity-100"
                    : "motion-pop -rotate-12 scale-110 opacity-100"
                  : "scale-90 opacity-70",
              )}
              aria-hidden="true"
            />
          </button>
        );
      })}
    </div>
  );
}
