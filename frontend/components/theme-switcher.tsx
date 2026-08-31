"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useId, useSyncExternalStore } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useLocale } from "@/components/locale-provider";
import { cn } from "@/lib/utils";
import { captureProductEvent } from "@/components/posthog-analytics";

export function ThemeSwitcher({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const { pick } = useLocale();
  const instanceId = useId();
  const reduceMotion = useReducedMotion();
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const activeTheme = mounted ? (theme ?? "light") : "light";

  return (
    <div
      className={cn("glass-control inline-flex h-11 items-center rounded-full p-1", className)}
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
              "group relative isolate grid size-9 place-items-center overflow-hidden rounded-full text-muted-foreground outline-none transition-[color,transform] duration-300",
              "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-transparent active:scale-95",
              active && "text-foreground",
            )}
          >
            {active ? (
              <motion.span
                layoutId={`theme-glass-selection-${instanceId}`}
                className="glass-selection absolute inset-0 -z-10 rounded-full"
                transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 36, mass: 0.7 }}
              />
            ) : null}
            <Icon
              className={cn(
                "relative z-10 size-3.5 transition-[transform,opacity] duration-500",
                active
                  ? value === "light"
                    ? "rotate-90 scale-110 opacity-100"
                    : "-rotate-12 scale-110 opacity-100"
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
