"use client";

import { Suspense } from "react";
import { isSupabaseConfigured } from "@/lib/env";
import { LoginForm } from "@/components/auth/login-form";
import { BrandMark } from "@/components/brand-mark";
import { BookOpenIcon, CalendarDaysIcon, MapPinnedIcon, SparklesIcon } from "lucide-react";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { useLocale } from "@/components/locale-provider";

export default function LoginPage() {
  const { pick } = useLocale();

  return (
    <main className="campus-grid relative min-h-svh overflow-x-hidden px-3 py-3 sm:px-8 sm:py-8">
      <div className="pointer-events-none absolute -right-28 -top-28 size-96 rounded-full bg-primary/10 blur-3xl" />
      <LocaleSwitcher className="absolute right-5 top-5 z-20 sm:right-12 sm:top-12" />
      <div className="relative mx-auto grid min-h-[calc(100svh-1.5rem)] min-w-0 max-w-6xl overflow-hidden rounded-2xl border border-black/10 bg-card/90 shadow-[0_24px_80px_rgb(55_37_26/14%)] backdrop-blur-sm sm:min-h-[calc(100svh-4rem)] sm:rounded-[2rem] lg:grid-cols-[1.08fr_0.92fr]">
        <section className="relative flex min-w-0 flex-col justify-between overflow-hidden bg-[#181513] p-5 text-white sm:p-10 lg:p-14">
          <div className="absolute -bottom-28 -right-24 size-80 rounded-full border-[42px] border-primary/30" />
          <div className="relative flex items-center gap-3">
            <BrandMark />
            <div>
              <p className="font-bold leading-none tracking-tight">devrimo</p>
              <p className="mt-1 text-[10px] font-semibold tracking-[0.18em] text-white/45 uppercase">{pick({ tr: "ODTÜ öğrenci asistanı", en: "AI assistant for METU" })}</p>
            </div>
          </div>

          <div className="relative my-10 min-w-0 max-w-xl sm:my-16 lg:my-8">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/70">
              <SparklesIcon className="size-3.5 text-primary" />
              {pick({ tr: "Kampüsteki yeni çalışma arkadaşın", en: "Your new campus companion" })}
            </div>
            <h1 className="text-3xl font-semibold leading-[1.04] tracking-[-0.05em] min-[400px]:text-4xl sm:text-5xl lg:text-6xl">
              {pick({ tr: "ODTÜ hayatı,", en: "METU life," })}
              <span className="block text-primary">{pick({ tr: "biraz daha kolay.", en: "made simpler." })}</span>
            </h1>
            <p className="mt-5 max-w-lg text-sm leading-6 text-white/58 sm:text-base sm:leading-7">
              {pick({
                tr: "Ders planından kampüste boş sınıf bulmaya kadar, ihtiyacın olan bilgi tek yerde.",
                en: "From planning coursework to finding your way around campus, get the context you need in one place.",
              })}
            </p>
          </div>

          <div className="relative grid min-w-0 grid-cols-3 gap-2">
            {[{ icon: BookOpenIcon, label: pick({ tr: "Dersler", en: "Courses" }) }, { icon: CalendarDaysIcon, label: pick({ tr: "Takvim", en: "Calendar" }) }, { icon: MapPinnedIcon, label: pick({ tr: "Kampüs", en: "Campus" }) }].map(({ icon: Icon, label }) => (
              <div key={label} className="min-w-0 rounded-2xl border border-white/10 bg-white/[0.04] p-2.5 text-[11px] text-white/65 sm:p-4 sm:text-xs">
                <Icon className="mb-2 size-4 text-primary" />
                {label}
              </div>
            ))}
          </div>
        </section>

        <section className="flex min-w-0 items-center justify-center p-4 py-8 sm:p-10 lg:p-14">
          <div className="min-w-0 w-full max-w-md">
            {isSupabaseConfigured() ? (
              <Suspense>
                <LoginForm />
              </Suspense>
            ) : (
              <div className="rounded-3xl border bg-white/70 p-7 shadow-sm">
                <p className="text-xs font-bold tracking-[0.16em] text-primary uppercase">{pick({ tr: "Kurulum gerekli", en: "Setup required" })}</p>
                <h2 className="mt-3 text-2xl font-semibold tracking-tight">{pick({ tr: "Giriş bağlantısını tamamla", en: "Connect authentication" })}</h2>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  {pick({ tr: "Giriş ekranını etkinleştirmek için Supabase bilgilerini", en: "Add your Supabase credentials to" })} <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">.env.local</code>{pick({ tr: " dosyasına ekle.", en: " to enable sign-in." })}
                </p>
                <div className="mt-5 space-y-2 rounded-2xl bg-[#181513] p-4 font-mono text-xs text-white/70">
                  <p>NEXT_PUBLIC_SUPABASE_URL</p>
                  <p>NEXT_PUBLIC_SUPABASE_ANON_KEY</p>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
