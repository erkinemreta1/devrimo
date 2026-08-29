"use client";

import { MessageSquarePlusIcon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/types";

export function SessionSidebar({
  sessions,
  activeId,
  onNewChat,
  onSelect,
  onDelete,
}: {
  sessions: ChatSession[];
  activeId?: string;
  onNewChat: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}) {
  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r bg-sidebar">
      <div className="p-3">
        <Button className="w-full justify-start" variant="outline" onClick={onNewChat}>
          <MessageSquarePlusIcon />
          New chat
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-1 px-2 pb-3">
          {sessions.length === 0 ? (
            <p className="px-2 py-6 text-sm text-muted-foreground">No sessions yet.</p>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={cn(
                  "group flex items-center rounded-lg",
                  activeId === session.id && "bg-sidebar-accent",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
                  onClick={() => onSelect(session.id)}
                >
                  {session.title?.trim() || "Untitled chat"}
                </button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="mr-1 opacity-0 group-hover:opacity-100"
                  onClick={() => onDelete(session.id)}
                  aria-label="Delete session"
                >
                  <Trash2Icon />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </aside>
  );
}
