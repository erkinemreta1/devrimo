"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ChatMessage, ChatSession } from "@/lib/types";

async function parseError(response: Response) {
  const body = await response.json().catch(() => null);
  const message =
    (body && typeof body === "object" && "error" in body && typeof body.error === "string"
      ? body.error
      : null) || response.statusText;
  throw new Error(message);
}

export function useChatSessions() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: async () => {
      const response = await fetch("/api/sessions");
      if (!response.ok) await parseError(response);
      const data = (await response.json()) as { sessions: ChatSession[] };
      return data.sessions ?? [];
    },
  });

  const remove = useMutation({
    mutationFn: async (sessionId: string) => {
      const response = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
      if (!response.ok) await parseError(response);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["chat-sessions"] }),
  });

  return {
    sessions: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    remove,
  };
}

export async function loadSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  const response = await fetch(`/api/sessions/${sessionId}`);
  if (!response.ok) await parseError(response);
  const data = (await response.json()) as { messages: ChatMessage[] };
  return data.messages ?? [];
}
