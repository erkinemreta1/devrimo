"use client";

import { CheckIcon, ShieldAlertIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLocale } from "@/components/locale-provider";
import type { CampusTool } from "@/lib/types";

/**
 * One campus MCP server, as a card the student switches on or off.
 *
 * The scope line is always visible rather than tucked behind a disclosure:
 * these tools sign in to METU as the student, and one of them can send mail
 * as them, so what they can reach is the decision — not a detail.
 */
export function CampusToolToggle({
  tool,
  checked,
  onChange,
  disabled = false,
}: {
  tool: CampusTool;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}) {
  const { locale } = useLocale();
  const name = locale === "tr" ? tool.name_tr : tool.name_en;
  const description = locale === "tr" ? tool.description_tr : tool.description_en;
  const scope = locale === "tr" ? tool.scope_tr : tool.scope_en;
  const canWrite = tool.id === "webmail";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border p-3.5 text-left transition-colors",
        "hover:bg-accent/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
        checked ? "border-primary bg-primary/5" : "border-border",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
          checked ? "border-primary bg-primary text-primary-foreground" : "border-input",
        )}
        aria-hidden
      >
        {checked ? <CheckIcon className="size-3.5" /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{name}</span>
          {canWrite ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold tracking-wide text-amber-700 uppercase dark:text-amber-400">
              <ShieldAlertIcon className="size-3" />
              {locale === "tr" ? "Yazma izni" : "Can write"}
            </span>
          ) : null}
        </span>
        <span className="mt-1 block text-xs text-muted-foreground">{description}</span>
        <span className="mt-1.5 block text-[11px] leading-4 text-muted-foreground/80">{scope}</span>
      </span>
    </button>
  );
}
