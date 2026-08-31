"use client";

import {
  MessageSquarePlusIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  Trash2Icon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/types";
import { useLocale } from "@/components/locale-provider";

export function SessionSidebar({
  sessions,
  activeId,
  onNewChat,
  onSelect,
  onDelete,
  className,
  collapsed = false,
  onToggleCollapse,
}: {
  sessions: ChatSession[];
  activeId?: string;
  onNewChat: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
  className?: string;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const { pick } = useLocale();
  return (
    <aside aria-label={pick({ tr: "Sohbet geçmişi", en: "Chat history" })} className={cn("motion-sidebar flex h-full min-w-0 flex-col bg-sidebar/88", className)}>
      <div className={cn("border-b p-3", collapsed && "flex flex-col items-center gap-2 px-2")}>
        {onToggleCollapse ? (
          <div className={cn("mb-2 flex items-center justify-between", collapsed && "mb-0")}>
            {!collapsed ? (
              <div>
                <p className="text-sm font-semibold">{pick({ tr: "Sohbetler", en: "Chats" })}</p>
                <p className="text-[11px] text-muted-foreground">{sessions.length} {pick({ tr: "sohbet", en: sessions.length === 1 ? "conversation" : "conversations" })}</p>
              </div>
            ) : null}
            <Button variant="ghost" size="icon-sm" onClick={onToggleCollapse} aria-label={collapsed ? pick({ tr: "Sohbet kenar çubuğunu aç", en: "Expand chat sidebar" }) : pick({ tr: "Sohbet kenar çubuğunu daralt", en: "Collapse chat sidebar" })}>
              {collapsed ? <PanelLeftOpenIcon /> : <PanelLeftCloseIcon />}
            </Button>
          </div>
        ) : null}
        <Button className={cn("w-full justify-start", collapsed && "size-9 justify-center px-0")} variant="outline" onClick={onNewChat} aria-label={collapsed ? pick({ tr: "Yeni sohbet", en: "New chat" }) : undefined}>
          <MessageSquarePlusIcon />
          {!collapsed ? pick({ tr: "Yeni sohbet", en: "New chat" }) : null}
        </Button>
      </div>
      {!collapsed ? <ScrollArea className="min-h-0 flex-1">
        <nav aria-label={pick({ tr: "Sohbetler", en: "Chats" })} className="flex flex-col gap-1 px-2 pb-3">
          {sessions.length === 0 ? (
            <p className="px-2 py-6 text-sm text-muted-foreground">{pick({ tr: "İlk sohbetini başlat.", en: "Start your first conversation." })}</p>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={cn(
                  "group flex min-h-11 items-center rounded-lg transition-colors duration-200",
                  activeId === session.id && "bg-sidebar-accent shadow-[inset_3px_0_0_var(--primary)]",
                )}
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm"
                  onClick={() => onSelect(session.id)}
                  aria-current={activeId === session.id ? "page" : undefined}
                >
                  {session.title?.trim() || pick({ tr: "İsimsiz sohbet", en: "Untitled chat" })}
                </button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="mr-1 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100 lg:focus-visible:opacity-100"
                  onClick={() => onDelete(session.id)}
                  aria-label={pick({ tr: "Sohbeti sil", en: "Delete chat" })}
                >
                  <Trash2Icon />
                </Button>
              </div>
            ))
          )}
        </nav>
      </ScrollArea> : <div className="flex-1" />}
      {!collapsed ? (
        <p className="border-t px-4 py-3 text-[11px] leading-4 text-muted-foreground">
          {pick({ tr: "Sohbet geçmişin yalnızca hesabına bağlıdır.", en: "Your chat history belongs only to your account." })}
        </p>
      ) : null}
    </aside>
  );
}
