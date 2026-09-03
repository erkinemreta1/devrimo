import { OnboardingGate } from "@/components/onboarding/onboarding-gate";
import { ChatShell } from "@/components/chat/chat-shell";

export default function HomePage() {
  return (
    <div className="h-full min-h-0">
      <OnboardingGate>
        <ChatShell />
      </OnboardingGate>
    </div>
  );
}
