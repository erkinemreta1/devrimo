"use client";

import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/components/locale-provider";
import { resetStudent } from "@/components/posthog-analytics";

export function SignOutButton() {
  const { pick } = useLocale();
  const router = useRouter();

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    // Before the redirect: on a shared machine the next person to sign in
    // would otherwise inherit this student's identity and their events.
    resetStudent();
    router.replace("/login");
    router.refresh();
  }

  return (
    <Button variant="outline" size="sm" onClick={signOut}>
      {pick({ tr: "Çıkış", en: "Sign out" })}
    </Button>
  );
}
