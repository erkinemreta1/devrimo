import { Suspense } from "react";
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
  return (
    <Suspense fallback={<div className="min-h-0 flex-1 animate-pulse bg-muted/30" />}>
      <AdminDashboard principal={principal} />
    </Suspense>
  );
}
