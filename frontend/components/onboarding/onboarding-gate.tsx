"use client";

import { useState, type ReactNode } from "react";
import { Loader2Icon } from "lucide-react";
import { useProfile } from "@/hooks/useProfile";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";

/**
 * Shows the first-run wizard until the student has completed it.
 *
 * Deliberately wraps the provisioning gate rather than sitting inside it: the
 * wizard collects connection and privacy choices before the private assistant
 * is prepared, so its first run already reflects the student's consent.
 *
 * A failed profile fetch falls through to the app instead of trapping the
 * student on a wizard they can't complete; onboarding is re-offered from
 * Settings.
 */
export function OnboardingGate({ children }: { children: ReactNode }) {
  const { profile, isLoading, error, refetch } = useProfile();
  const [dismissed, setDismissed] = useState(false);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!error && profile && !profile.onboarding_completed && !dismissed) {
    return (
      <OnboardingFlow
        onDone={() => {
          setDismissed(true);
          void refetch();
        }}
      />
    );
  }

  return <>{children}</>;
}
