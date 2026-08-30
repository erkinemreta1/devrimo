"use client";

import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/components/locale-provider";
import { ONBOARDING_STEPS, stepLabel } from "@/components/onboarding/steps";

export function StepIndicator({ current }: { current: number }) {
  const { locale } = useLocale();

  return (
    <ol className="flex items-center justify-center gap-1.5 sm:gap-2">
      {ONBOARDING_STEPS.map((step, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <li key={step} className="flex items-center gap-1.5 sm:gap-2">
            <span
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors",
                done && "border-primary bg-primary text-primary-foreground",
                active && "border-primary text-primary",
                !done && !active && "border-border text-muted-foreground",
              )}
              aria-hidden
            >
              {done ? <CheckIcon className="size-3.5" /> : index + 1}
            </span>
            <span
              className={cn(
                "hidden text-xs font-medium sm:inline",
                active ? "text-foreground" : "text-muted-foreground",
              )}
            >
              {stepLabel(step, locale)}
            </span>
            {index < ONBOARDING_STEPS.length - 1 ? (
              <span className={cn("h-px w-4 sm:w-8", done ? "bg-primary" : "bg-border")} aria-hidden />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
