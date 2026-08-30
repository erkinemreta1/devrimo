"use client";

import { usePathname } from "next/navigation";
import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import { useEffect, type ReactNode } from "react";

const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST;

let isInitialized = false;

type ProductEventProperties = {
  page_exited: { path: string; duration_seconds: number };
  chat_new_clicked: Record<string, never>;
  chat_opened: { source: "history" };
  chat_delete_requested: { was_active: boolean };
  chat_deleted: { was_active: boolean };
  chat_message_sent: {
    conversation_type: "new" | "existing";
    message_position: number;
    text_length: number;
    attachment_count: number;
  };
  chat_response_completed: { duration_seconds: number };
  chat_response_error: { category: "busy" | "other"; duration_seconds: number | null };
  agent_action_confirmation: { approved: boolean; tool: string };
  theme_changed: { theme: "light" | "dark" };
  language_changed: { locale: "tr" | "en" };
  onboarding_step_viewed: { step: "welcome" | "connect" | "tools" | "ready" };
  onboarding_connection_result: { result: "success" | "error"; verification_skipped: boolean };
  onboarding_tool_selection_saved: { tool_count: number; result: "success" | "error" };
  onboarding_finished: { path: "completed" | "skipped" };
};

function initializePostHog() {
  if (isInitialized) return true;
  if (!posthogKey || !posthogHost) return false;

  posthog.init(posthogKey, {
    api_host: posthogHost,
    autocapture: false,
    capture_pageview: false,
    capture_pageleave: false,
    disable_session_recording: true,
    disable_surveys: true,
    person_profiles: "never",
  });

  isInitialized = true;
  return true;
}

export function captureProductEvent<EventName extends keyof ProductEventProperties>(
  event: EventName,
  properties: ProductEventProperties[EventName],
) {
  if (!initializePostHog()) return;
  posthog.capture(event, properties);
}

function AnonymousPageView() {
  const pathname = usePathname();

  useEffect(() => {
    if (!initializePostHog()) return;

    const enteredAt = Date.now();

    // Deliberately exclude the query string: it can contain auth/navigation data.
    posthog.capture("$pageview", {
      $current_url: `${window.location.origin}${pathname}`,
    });

    return () => {
      captureProductEvent("page_exited", {
        path: pathname,
        duration_seconds: Math.max(0, Math.round((Date.now() - enteredAt) / 1000)),
      });
    };
  }, [pathname]);

  return null;
}

export function PostHogAnalytics({ children }: { children: ReactNode }) {
  return (
    <PostHogProvider client={posthog}>
      <AnonymousPageView />
      {children}
    </PostHogProvider>
  );
}
