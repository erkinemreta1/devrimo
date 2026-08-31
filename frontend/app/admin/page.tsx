import { apiFetch } from "@/lib/api/client";
import { getAuth } from "@/lib/supabase/server";
import type { AdminPrincipal } from "@/lib/admin/types";
import { AdminDashboard } from "@/components/admin/admin-dashboard";

export default async function AdminPage() {
  const auth = await getAuth();
  if (!auth) return null;
  const principal = await apiFetch<AdminPrincipal>("/admin/me", {
    token: auth.accessToken,
    cache: "no-store",
  });
  return <AdminDashboard principal={principal} />;
}
