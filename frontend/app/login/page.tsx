import { Suspense } from "react";
import { isSupabaseConfigured } from "@/lib/env";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center bg-muted/40 px-4 py-10">
      <div className="mb-8 text-center">
        <p className="text-sm font-medium tracking-[0.2em] text-muted-foreground">DEVRIMO</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">Your private coding agent</h1>
      </div>
      {isSupabaseConfigured() ? (
        <Suspense>
          <LoginForm />
        </Suspense>
      ) : (
        <div className="max-w-md rounded-xl border bg-card p-6 text-sm text-muted-foreground">
          Add <code className="text-foreground">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="text-foreground">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to{" "}
          <code className="text-foreground">.env.local</code> to enable login.
        </div>
      )}
    </main>
  );
}
