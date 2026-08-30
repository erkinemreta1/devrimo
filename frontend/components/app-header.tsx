"use client";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from "next/link";
import { SignOutButton } from "@/components/auth/sign-out-button";
import { BrandMark } from "@/components/brand-mark";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { useLocale } from "@/components/locale-provider";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { HomeIcon } from "lucide-react";

export function AppHeader({ email }: { email?: string | null }) {
  const { pick } = useLocale();
  return (
    <header className="motion-header relative flex h-16 shrink-0 items-center justify-between gap-3 border-b bg-card/75 px-4 backdrop-blur-xl after:absolute after:inset-x-0 after:bottom-[-1px] after:h-px after:bg-gradient-to-r after:from-transparent after:via-primary/45 after:to-transparent">
      <div className="flex items-center gap-3">
        <Link href="/" className="group flex items-center gap-2 font-semibold tracking-tight">
          <BrandMark className="size-8 rounded-lg shadow-[0_3px_0_#9b1026] transition-transform duration-200 group-hover:rotate-0 group-hover:scale-105" />
          devrimo
        </Link>
      </div>
      <div className="flex items-center gap-2">
        <ThemeSwitcher />
        <LocaleSwitcher />
        {email ? <span className="hidden text-sm text-muted-foreground sm:inline">{email}</span> : null}
        <Link href="/" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
          <HomeIcon aria-hidden="true" />
          <span className="sr-only sm:not-sr-only">{pick({ tr: "Ana sayfa", en: "Home" })}</span>
        </Link>
        <Link href="/settings" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>
          {pick({ tr: "Ayarlar", en: "Settings" })}
        </Link>
        <SignOutButton />
      </div>
    </header>
  );
}
