import { redirect } from "next/navigation";
import { getAuth } from "@/lib/supabase/server";
import { isSupabaseConfigured } from "@/lib/env";
import { AppHeader } from "@/components/app-header";

export const dynamic = "force-dynamic";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!isSupabaseConfigured()) {
    redirect("/login");
  }

  const auth = await getAuth();
  if (!auth) {
    redirect("/login");
  }

  return (
    <div className="flex h-svh min-h-0 flex-col">
      <a
        href="#main-content"
        className="sr-only z-50 rounded-md bg-background px-4 py-2 font-medium text-foreground shadow-lg focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:ring-2 focus:ring-ring"
      >
        Ana içeriğe geç
      </a>
      <AppHeader email={auth.user.email} />
      <main id="main-content" tabIndex={-1} className="min-h-0 flex-1 outline-none">
        {children}
      </main>
    </div>
  );
}
