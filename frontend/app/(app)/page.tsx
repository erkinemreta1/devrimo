import { ProvisioningGate } from "@/components/agent/provisioning-gate";
import { ChatShell } from "@/components/chat/chat-shell";

export default function HomePage() {
  return (
    <div className="h-full min-h-0">
      <ProvisioningGate>
        <ChatShell />
      </ProvisioningGate>
    </div>
  );
}
