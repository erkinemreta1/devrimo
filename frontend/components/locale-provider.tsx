"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Locale = "tr" | "en";

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  pick: (copy: { tr: string; en: string }) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("tr");

  useEffect(() => {
    const saved = window.localStorage.getItem("devrimo-locale");
    if (saved === "tr" || saved === "en") {
      queueMicrotask(() => {
        setLocaleState(saved);
        document.documentElement.lang = saved;
      });
    }
  }, []);

  function setLocale(nextLocale: Locale) {
    setLocaleState(nextLocale);
    window.localStorage.setItem("devrimo-locale", nextLocale);
    document.documentElement.lang = nextLocale;
  }

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, pick: (copy) => copy[locale] }),
    [locale],
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used within LocaleProvider");
  return context;
}
