import type { Locale } from "@/components/locale-provider";

/**
 * The wizard's steps, in order.
 *
 * The id is persisted on the profile as `onboarding_step` so a student who
 * closes the tab mid-flow comes back to where they were. Reordering or
 * renaming a step is safe: an unrecognized stored id falls back to the first
 * step rather than erroring (see `stepIndex`).
 */
export const ONBOARDING_STEPS = ["welcome", "connect", "privacy", "ready"] as const;

export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];

export function stepIndex(step: string | null | undefined): number {
  const normalized = step === "tools" ? "privacy" : step;
  const index = ONBOARDING_STEPS.indexOf((normalized ?? "") as OnboardingStep);
  return index === -1 ? 0 : index;
}

export function stepLabel(step: OnboardingStep, locale: Locale): string {
  const labels: Record<OnboardingStep, { tr: string; en: string }> = {
    welcome: { tr: "Tanışalım", en: "Welcome" },
    connect: { tr: "ODTÜ hesabı", en: "METU account" },
    privacy: { tr: "Veri erişimi", en: "Data access" },
    ready: { tr: "Hazır", en: "Ready" },
  };
  return labels[step][locale];
}
