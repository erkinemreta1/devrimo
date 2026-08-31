"use client";

import posthog from "posthog-js";
import { PostHogProvider } from "posthog-js/react";
import { type ReactNode } from "react";

/**
 * The product event contract.
 *
 * This map is the single source of truth for event names *and* their property
 * shapes — adding a property here and forgetting it at a call site is a
 * compile error, which is the only reliable way to keep an event schema honest
 * across a codebase.
 *
 * Initialisation lives in `instrumentation-client.ts`, not here: pageviews,
 * autocapture, session replay and exception capture all need the SDK live
 * before the first render.
 */
type ProductEventProperties = {
  // --- chat ---------------------------------------------------------------
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
  chat_response_error: {
    category: "busy" | "network" | "other";
    status: number | null;
    error_code: string | null;
    duration_seconds: number | null;
  };
  // Tool activity the broker streams as `devrimo` extension chunks. The
  // frontend received these already and threw them away.
  agent_tool_call: { tool: string | null; server: string | null; status: "started" | "completed" | "error" };
  // The denominator for the approve/reject funnel: without it, a confirmation
  // the student simply abandoned is indistinguishable from one never shown.
  chat_confirmation_shown: { tool: string | null };
  agent_action_confirmation: { approved: boolean; tool: string };

  // --- agent + campus -----------------------------------------------------
  agent_provisioned: { result: "success" | "error" };
  campus_connection_saved: { source: "onboarding" | "settings"; result: "success" | "error"; verification_skipped: boolean };
  campus_tools_changed: { source: "onboarding" | "settings"; tool_count: number; result: "success" | "error" };
  campus_disconnected: { result: "success" | "error" };

  // --- onboarding + preferences ------------------------------------------
  onboarding_step_viewed: { step: "welcome" | "connect" | "tools" | "ready" };
  onboarding_connection_result: { result: "success" | "error"; verification_skipped: boolean };
  onboarding_tool_selection_saved: { tool_count: number; result: "success" | "error" };
  onboarding_finished: { path: "completed" | "skipped" };
  theme_changed: { theme: "light" | "dark" };
  language_changed: { locale: "tr" | "en" };
  settings_opened: Record<string, never>;
};

export type StudentIdentityProperties = {
  name?: string | null;
  user_name?: string | null;
  department?: string | null;
};

function isReady() {
  return typeof window !== "undefined" && posthog.__loaded;
}

export function captureProductEvent<EventName extends keyof ProductEventProperties>(
  event: EventName,
  properties: ProductEventProperties[EventName],
) {
  if (!isReady()) return;
  posthog.capture(event, properties);
}

/**
 * Report a handled error that would otherwise only become a toast.
 *
 * The app catches almost everything and shows a `sonner` message, which is
 * right for the student and useless for us — these calls are what make those
 * failures countable.
 */
export function captureError(error: unknown, context: Record<string, unknown> = {}) {
  if (!isReady()) return;
  const exception = error instanceof Error ? error : new Error(String(error));
  posthog.captureException(exception, context);
}

/**
 * Link this browser to a student.
 *
 * The Supabase user id links events to the right person. Profile data is
 * supplied when it becomes available; email is deliberately excluded because
 * the broker already holds it and PostHog has no need for it.
 */
export function identifyStudent(userId: string, properties: StudentIdentityProperties = {}) {
  if (!isReady() || !userId) return;
  const personProperties = Object.fromEntries(
    Object.entries(properties).filter(([, value]) => typeof value === "string" && value.trim().length > 0),
  );
  posthog.identify(userId, personProperties);
}

/**
 * Break the link on sign-out.
 *
 * Without this, the next person to use a shared machine — a lab computer, a
 * friend's laptop — inherits the previous student's identity and their events
 * land on the wrong person.
 */
export function resetStudent() {
  if (!isReady()) return;
  posthog.reset();
}

export function PostHogAnalytics({ children }: { children: ReactNode }) {
  return <PostHogProvider client={posthog}>{children}</PostHogProvider>;
}
