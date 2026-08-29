import { createUIMessageStream, createUIMessageStreamResponse } from "ai";
import type { UIMessage } from "ai";
import { streamChatCompletions } from "@/lib/api/chat";
import { requireAuth } from "@/lib/api/route-utils";
import type { ChatMessage, ChatRole } from "@/lib/types";

function textFromParts(message: UIMessage) {
  return message.parts
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function toChatMessages(messages: UIMessage[]): ChatMessage[] {
  return messages
    .filter((message) => message.role === "user" || message.role === "assistant" || message.role === "system")
    .map((message) => ({
      role: message.role as ChatRole,
      content: textFromParts(message),
    }))
    .filter((message) => message.content.trim().length > 0);
}

export const maxDuration = 600;

export async function POST(request: Request) {
  const result = await requireAuth();
  if ("error" in result) return result.error;

  const body = (await request.json()) as {
    messages?: UIMessage[];
    id?: string;
  };

  const messages = toChatMessages(body.messages ?? []);
  const clientId = body.id;
  const textId = "assistant-text";

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      writer.write({ type: "text-start", id: textId });
      try {
        for await (const delta of streamChatCompletions(result.auth.accessToken, {
          messages,
          client_id: clientId,
          stream: true,
        })) {
          writer.write({ type: "text-delta", id: textId, delta });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Chat failed";
        writer.write({ type: "error", errorText: message });
      }
      writer.write({ type: "text-end", id: textId });
    },
  });

  return createUIMessageStreamResponse({ stream });
}
