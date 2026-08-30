import { OnboardingGate } from "@/components/onboarding/onboarding-gate";
import { ProvisioningGate } from "@/components/agent/provisioning-gate";
import { ChatShell } from "@/components/chat/chat-shell";

export default function HomePage() {
  return (
    <div className="h-full min-h-0">
      {/*
        Onboarding runs before provisioning on purpose: it collects the campus
        credentials the agent container is built with, so finishing it first
        means the container is created with the student's tools already in it.
      */}
      <OnboardingGate>
        <ProvisioningGate>
          <ChatShell />
        </ProvisioningGate>
      </OnboardingGate>
    </div>
  );
}
