import { redirect } from "next/navigation";
import { AppHeader } from "@/components/app-header";
import { getAuth } from "@/lib/supabase/server";
import { apiFetch } from "@/lib/api/client";
import type { AdminPrincipal } from "@/lib/admin/types";

export const dynamic = "force-dynamic";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const auth = await getAuth();
  if (!auth) redirect("/login");

  try {
    await apiFetch<AdminPrincipal>("/admin/me", { token: auth.accessToken, cache: "no-store" });
  } catch {
    redirect("/");
  }

  return (
    <div className="flex min-h-svh flex-col">
      <AppHeader email={auth.user.email} />
      {children}
    </div>
  );
}
