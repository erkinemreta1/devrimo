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
      <AppHeader email={auth.user.email} />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
