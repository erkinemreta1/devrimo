"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";

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
      className={cn("inline-flex h-9 items-center rounded-xl border border-border bg-background/85 p-1 shadow-sm", className)}
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
            onClick={() => setTheme(value)}
            className={cn(
              "grid size-7 place-items-center rounded-lg text-muted-foreground transition-colors outline-none",
              "hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              active && "bg-foreground text-background shadow-sm hover:bg-foreground hover:text-background",
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}
