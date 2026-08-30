"use client";

import Link from "next/link";
import { CircleIcon, PlugZapIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCampus } from "@/hooks/useCampus";
import { useLocale } from "@/components/locale-provider";

/**
 * Which campus tools the assistant can actually reach right now.
 *
 * Reads live state rather than a static list, because "connected" and
 * "installed" are different things here: a tool the student enabled but has no
 * working credentials for is not something the assistant can use, and showing
 * it as available is how you get a student blaming the assistant for a
 * password problem.
 */
export function McpToolsList({ compact = false }: { compact?: boolean }) {
  const { pick, locale } = useLocale();
  const { connection, tools, isLoading } = useCampus();

  if (isLoading || tools.length === 0) return null;

  const active = tools.filter((tool) => tool.active);

  return (
    <section className={compact ? "px-3 pb-4" : undefined}>
      <div className="mb-2 flex items-center gap-1.5 px-1">
        <PlugZapIcon className="size-3.5 text-primary" />
        <p className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
          {pick({ tr: "Kampüs araçları", en: "Campus tools" })}
        </p>
      </div>

      {!connection?.connected ? (
        <Link
          href="/settings"
          className="block rounded-md px-2 py-1.5 text-xs leading-4 text-muted-foreground underline-offset-4 hover:underline"
        >
          {pick({
            tr: "ODTÜ hesabını bağlayarak ders, transkript ve duyurulara eriş.",
            en: "Connect your METU account to reach courses, transcript, and announcements.",
          })}
        </Link>
      ) : (
        <ul className="flex flex-col gap-1">
          {tools.map((tool) => (
            <li key={tool.id} className="flex items-start gap-2 rounded-md px-2 py-1.5 text-left">
              <CircleIcon
                className={cn(
                  "mt-1 size-2 shrink-0",
                  tool.active ? "fill-primary text-primary" : "fill-muted-foreground/30 text-muted-foreground/30",
                )}
                aria-hidden
              />
              <span className="min-w-0">
                <span className="block text-sm leading-none font-medium">
                  {locale === "tr" ? tool.name_tr : tool.name_en}
                </span>
                {!compact ? (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {locale === "tr" ? tool.description_tr : tool.description_en}
                  </span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}

      {connection?.connected && active.length === 0 ? (
        <Link
          href="/settings"
          className="mt-1 block rounded-md px-2 py-1.5 text-[11px] leading-4 text-muted-foreground underline-offset-4 hover:underline"
        >
          {pick({ tr: "Hiçbir araç açık değil — Ayarlar'dan seç.", en: "No tools are on — pick some in Settings." })}
        </Link>
      ) : null}
    </section>
  );
}
