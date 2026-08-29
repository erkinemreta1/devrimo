import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { AgentStatusChip } from "@/components/agent/agent-status-chip";

export function AppHeader({ email }: { email?: string | null }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b px-4">
      <div className="flex items-center gap-3">
        <Link href="/" className="font-semibold tracking-tight">
          Devrimo
        </Link>
        <AgentStatusChip />
      </div>
      <div className="flex items-center gap-2">
        {email ? <span className="hidden text-sm text-muted-foreground sm:inline">{email}</span> : null}
        <Link href="/settings" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
          Settings
        </Link>
        <SignOutButton />
      </div>
    </header>
  );
}
