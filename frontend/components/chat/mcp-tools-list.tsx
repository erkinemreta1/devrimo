"use client";

import { PlugZapIcon } from "lucide-react";
import { CAMPUS_MCP_TOOLS } from "@/lib/campus";

export function McpToolsList({ compact = false }: { compact?: boolean }) {
  return (
    <section className={compact ? "px-3 pb-4" : undefined}>
      <div className="mb-2 flex items-center gap-1.5 px-1">
        <PlugZapIcon className="size-3.5 text-primary" />
        <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
          Campus MCPs
        </p>
      </div>
      <ul className="flex flex-col gap-1">
        {CAMPUS_MCP_TOOLS.map((tool) => (
          <li
            key={tool.id}
            className="rounded-md px-2 py-1.5 text-left"
          >
            <p className="text-sm font-medium leading-none">{tool.name}</p>
            {!compact ? (
              <p className="mt-1 text-xs text-muted-foreground">{tool.description}</p>
            ) : (
              <p className="mt-0.5 text-[11px] text-muted-foreground">{tool.description}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
