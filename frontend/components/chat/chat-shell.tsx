"use client";

import { useMemo, useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import type { UIMessage } from "ai";
import { toast } from "sonner";
import { Thread } from "@/components/thread.aui";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { loadSessionMessages, useChatSessions } from "@/hooks/useChat";

function toUiMessages(sessionId: string, messages: { role: string; content: string; id?: string }[]): UIMessage[] {
  return messages.map((message, index) => ({
    id: message.id ?? `${sessionId}-${index}`,
    role: message.role as UIMessage["role"],
    parts: [{ type: "text", text: message.content }],
  }));
}

function AssistantThread({
  threadId,
  initialMessages,
  onThreadReady,
}: {
  threadId?: string;
  initialMessages?: UIMessage[];
  onThreadReady: (id: string | undefined) => void;
}) {
  const transport = useMemo(
    () =>
      new AssistantChatTransport({
        api: "/api/chat",
        prepareSendMessagesRequest: ({ id, messages }) => ({
          body: {
            id,
            session_id: id,
            messages,
          },
        }),
      }),
    [],
  );

  const runtime = useChatRuntime({
    id: threadId,
    messages: initialMessages,
    transport,
    onThreadIdChange: onThreadReady,
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Chat failed");
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}

export function ChatShell() {
  const { sessions, remove, refetch } = useChatSessions();
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [seedMessages, setSeedMessages] = useState<UIMessage[] | undefined>(undefined);
  const [chatKey, setChatKey] = useState(0);

  async function selectSession(sessionId: string) {
    try {
      const history = await loadSessionMessages(sessionId);
      setSeedMessages(toUiMessages(sessionId, history));
      setThreadId(sessionId);
      setChatKey((value) => value + 1);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load session");
    }
  }

  function newChat() {
    setSeedMessages([]);
    setThreadId(undefined);
    setChatKey((value) => value + 1);
  }

  async function deleteSession(sessionId: string) {
    if (!window.confirm("Delete this chat session?")) return;
    try {
      await remove.mutateAsync(sessionId);
      if (threadId === sessionId) newChat();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete session");
    }
  }

  return (
    <div className="flex h-full min-h-0">
      <SessionSidebar
        sessions={sessions}
        activeId={threadId}
        onNewChat={newChat}
        onSelect={selectSession}
        onDelete={deleteSession}
      />
      <div className="min-w-0 flex-1">
        <AssistantThread
          key={chatKey}
          threadId={threadId}
          initialMessages={seedMessages}
          onThreadReady={(nextId) => {
            setThreadId(nextId);
            void refetch();
          }}
        />
      </div>
    </div>
  );
}
