"use client";

import { useState } from "react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import type { UIMessage } from "ai";
import { toast } from "sonner";
import { Thread } from "@/components/thread.aui";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { loadSessionMessages, useChatSessions } from "@/hooks/useChat";
import { Loader2Icon, Trash2Icon } from "lucide-react";
import { useLocale } from "@/components/locale-provider";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { captureProductEvent } from "@/components/posthog-analytics";

function toUiMessages(sessionId: string, messages: { role: string; content: string; id?: string }[]): UIMessage[] {
  return messages.map((message, index) => ({
    id: message.id ?? `${sessionId}-${index}`,
    role: message.role as UIMessage["role"],
    parts: [{ type: "text", text: message.content }],
  }));
}

class ChatTelemetry {
  private requestStartedAt: number | null = null;

  readonly transport = new AssistantChatTransport({
    api: "/api/chat",
    prepareSendMessagesRequest: ({ id, messages }) => {
      const latestMessage = messages.at(-1);
      const textLength = latestMessage?.parts.reduce(
        (total, part) => total + (part.type === "text" ? part.text.length : 0),
        0,
      ) ?? 0;
      const attachmentCount = latestMessage?.parts.filter((part) => part.type === "file").length ?? 0;
      this.requestStartedAt = Date.now();
      captureProductEvent("chat_message_sent", {
        conversation_type: id ? "existing" : "new",
        message_position: messages.length,
        text_length: textLength,
        attachment_count: attachmentCount,
      });
      return { body: { id, messages } };
    },
  });

  finishDuration() {
    const startedAt = this.requestStartedAt;
    this.requestStartedAt = null;
    return startedAt ? Math.max(0, Math.round((Date.now() - startedAt) / 1000)) : null;
  }
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
  const [telemetry] = useState(() => new ChatTelemetry());

  const runtime = useChatRuntime({
    id: threadId,
    messages: initialMessages,
    transport: telemetry.transport,
    onThreadIdChange: onThreadReady,
    onFinish: () => {
      captureProductEvent("chat_response_completed", {
        duration_seconds: telemetry.finishDuration() ?? 0,
      });
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Chat failed";
      const busy = message.includes("409") || message.toLowerCase().includes("busy");
      captureProductEvent("chat_response_error", {
        category: busy ? "busy" : "other",
        duration_seconds: telemetry.finishDuration(),
      });
      toast.error(
        busy
          ? "Your agent is answering another message. Please wait."
          : message,
      );
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}

export function ChatShell() {
  const { pick } = useLocale();
  const { sessions, remove, refetch } = useChatSessions();
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [selectedSessionId, setSelectedSessionId] = useState<string | undefined>(undefined);
  const [seedMessages, setSeedMessages] = useState<UIMessage[] | undefined>(undefined);
  const [chatKey, setChatKey] = useState(0);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const pendingDeleteSession = sessions.find((session) => session.id === pendingDeleteId);

  async function selectSession(sessionId: string) {
    try {
      const history = await loadSessionMessages(sessionId);
      setSeedMessages(toUiMessages(sessionId, history));
      setThreadId(sessionId);
      setSelectedSessionId(sessionId);
      setChatKey((value) => value + 1);
      captureProductEvent("chat_opened", { source: "history" });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load session");
    }
  }

  function newChat() {
    setSeedMessages([]);
    setThreadId(undefined);
    setSelectedSessionId(undefined);
    setChatKey((value) => value + 1);
  }

  function startNewChat() {
    captureProductEvent("chat_new_clicked", {});
    newChat();
  }

  async function deleteSession(sessionId: string) {
    try {
      const wasActive = selectedSessionId === sessionId;
      await remove.mutateAsync(sessionId);
      if (wasActive) newChat();
      setPendingDeleteId(null);
      captureProductEvent("chat_deleted", { was_active: wasActive });
      toast.success(pick({ tr: "Sohbet silindi.", en: "Chat deleted." }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete session");
    }
  }

  return (
    <div className="flex h-full min-h-0">
      <SessionSidebar
        sessions={sessions}
        activeId={selectedSessionId}
        onNewChat={startNewChat}
        onSelect={selectSession}
        onDelete={(sessionId) => {
          captureProductEvent("chat_delete_requested", {
            was_active: selectedSessionId === sessionId,
          });
          setPendingDeleteId(sessionId);
        }}
      />
      <div className="min-w-0 flex-1">
        <AssistantThread
          key={chatKey}
          threadId={threadId}
          initialMessages={seedMessages}
          onThreadReady={(nextId) => {
            setThreadId(nextId);
            if (!selectedSessionId && nextId) setSelectedSessionId(nextId);
            void refetch();
          }}
        />
      </div>
      <AlertDialog
        open={Boolean(pendingDeleteId)}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setPendingDeleteId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-destructive/10 text-destructive">
              <Trash2Icon />
            </AlertDialogMedia>
            <AlertDialogTitle>
              {pick({ tr: "Bu sohbet silinsin mi?", en: "Delete this chat?" })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDeleteSession?.title?.trim()
                ? pick({
                    tr: `“${pendingDeleteSession.title}” kalıcı olarak silinecek. Bu işlem geri alınamaz.`,
                    en: `“${pendingDeleteSession.title}” will be permanently deleted. This action cannot be undone.`,
                  })
                : pick({
                    tr: "Bu sohbet kalıcı olarak silinecek. Bu işlem geri alınamaz.",
                    en: "This chat will be permanently deleted. This action cannot be undone.",
                  })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              {pick({ tr: "Vazgeç", en: "Cancel" })}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending || !pendingDeleteId}
              onClick={() => {
                if (pendingDeleteId) void deleteSession(pendingDeleteId);
              }}
            >
              {remove.isPending ? <Loader2Icon className="animate-spin" /> : <Trash2Icon />}
              {pick({ tr: "Sohbeti sil", en: "Delete chat" })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
