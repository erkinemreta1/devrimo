"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { LocaleProvider } from "@/components/locale-provider";
import { ThemeProvider } from "next-themes";
import { PostHogAnalytics } from "@/components/posthog-analytics";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            retry: 1,
          },
        },
      }),
  );

  return (
    <PostHogAnalytics>
      <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} storageKey="devrimo-theme">
        <LocaleProvider>
          <QueryClientProvider client={queryClient}>
            <TooltipProvider>
              {children}
              <Toaster />
            </TooltipProvider>
          </QueryClientProvider>
        </LocaleProvider>
      </ThemeProvider>
    </PostHogAnalytics>
  );
}
