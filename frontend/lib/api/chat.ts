import { apiFetch, asList } from "@/lib/api/client";
import { getApiBaseUrl } from "@/lib/env";
import type { ChatCompletionsRequest, ChatMessage, ChatSession } from "@/lib/types";

export type ChatConfirmationRequirement = {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
};

export type ChatConfirmation = {
  run_id: string;
  session_id: string;
  requirements: ChatConfirmationRequirement[];
};

export type ChatStreamEvent =
  | { type: "text"; delta: string }
  | { type: "confirmation"; confirmation: ChatConfirmation };

export type ChatContinuation = {
  text: string;
  confirmation: ChatConfirmation | null;
};

export function listChatSessions(token: string) {
  return apiFetch<unknown>("/chat/sessions", { token }).then((data) =>
    asList<ChatSession>(data, ["sessions", "items", "data", "results"]),
  );
}

export async function getChatSession(token: string, sessionId: string) {
  const data = await apiFetch<unknown>(`/chat/sessions/${sessionId}`, { token });
  const messages = asList<ChatMessage>(data, ["messages", "items", "data"]);
  const session =
    data && typeof data === "object" && !Array.isArray(data)
      ? (data as ChatSession & { messages?: ChatMessage[] })
      : undefined;

  return {
    session: session ?? { id: sessionId },
    messages,
  };
}

export function deleteChatSession(token: string, sessionId: string) {
  return apiFetch<void>(`/chat/sessions/${sessionId}`, { method: "DELETE", token });
}

function parseSseEvent(data: string): ChatStreamEvent | null {
  if (!data || data === "[DONE]") return null;
  try {
    const json = JSON.parse(data) as {
      choices?: Array<{ delta?: { content?: string }; message?: { content?: string } }>;
      devrimo?: {
        type?: string;
        run_id?: string;
        session_id?: string;
        requirements?: ChatConfirmationRequirement[];
      };
    };
    if (
      json.devrimo?.type === "confirmation_required" &&
      json.devrimo.run_id &&
      json.devrimo.session_id
    ) {
      return {
        type: "confirmation",
        confirmation: {
          run_id: json.devrimo.run_id,
          session_id: json.devrimo.session_id,
          requirements: json.devrimo.requirements ?? [],
        },
      };
    }
    const delta = json.choices?.[0]?.delta?.content ?? json.choices?.[0]?.message?.content ?? "";
    return delta ? { type: "text", delta } : null;
  } catch {
    return null;
  }
}

export async function* streamChatCompletions(
  token: string,
  request: ChatCompletionsRequest,
): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/chat/completions`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      // The broker picks the model from AGENT_MODEL; this is only a label
      // echoed back on each chunk.
      model: request.model ?? "devrimo",
      messages: request.messages.map(({ role, content }) => ({ role, content })),
      session_id: request.client_id,
      stream: true,
    }),
  });

  if (!response.ok || !response.body) {
    const payload = await response.text().catch(() => "");
    if (response.status === 409) {
      throw new Error("Your agent is answering another message. Please wait.");
    }
    let message = payload;
    try {
      const parsed = JSON.parse(payload) as { detail?: string; message?: string; error?: string };
      message = parsed.detail ?? parsed.message ?? parsed.error ?? payload;
    } catch {}
    throw new Error(message || `Chat request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const data = trimmed.slice(5).trim();
      if (data === "[DONE]") return;
      const event = parseSseEvent(data);
      if (event) yield event;
    }
  }
}

export async function continueChatRun(
  token: string,
  confirmation: ChatConfirmation,
  requirementId: string,
  approved: boolean,
): Promise<ChatContinuation> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/chat/confirmations`, {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      run_id: confirmation.run_id,
      session_id: confirmation.session_id,
      requirement_id: requirementId,
      approved,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error((await response.text().catch(() => "")) || `Confirmation failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  let nextConfirmation: ChatConfirmation | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const event = parseSseEvent(trimmed.slice(5).trim());
      if (event?.type === "text") text += event.delta;
      if (event?.type === "confirmation") nextConfirmation = event.confirmation;
    }
  }
  return { text, confirmation: nextConfirmation };
}
