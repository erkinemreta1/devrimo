"use client";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { AgentStatusChip } from "@/components/agent/agent-status-chip";
import { BrandMark } from "@/components/brand-mark";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { useLocale } from "@/components/locale-provider";
import { ThemeSwitcher } from "@/components/theme-switcher";

export function AppHeader({ email }: { email?: string | null }) {
  const { pick } = useLocale();
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b bg-card/75 px-4 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <BrandMark className="size-8 rounded-lg shadow-[0_3px_0_#9b1026]" />
          devrimo
        </Link>
        <AgentStatusChip />
      </div>
      <div className="flex items-center gap-2">
        <ThemeSwitcher />
        <LocaleSwitcher />
        {email ? <span className="hidden text-sm text-muted-foreground sm:inline">{email}</span> : null}
        <Link href="/settings" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
          {pick({ tr: "Ayarlar", en: "Settings" })}
        </Link>
        <SignOutButton />
      </div>
    </header>
  );
}
