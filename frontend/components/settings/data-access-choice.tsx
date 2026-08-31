"use client";

import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export function DataAccessChoice({
  id,
  icon: Icon,
  title,
  description,
  detail,
  checked,
  onCheckedChange,
  disabled,
  optionalLabel,
}: {
  id: string;
  icon: LucideIcon;
  title: string;
  description: string;
  detail: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  optionalLabel: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_1fr_auto] gap-3 rounded-xl border p-4 transition-[border-color,background-color,box-shadow]",
        checked
          ? "border-primary/35 bg-primary/[0.045] shadow-[0_10px_28px_rgb(79_43_35/6%)]"
          : "border-border/80 bg-background/45",
      )}
    >
      <span className={cn("grid size-9 place-items-center rounded-lg", checked ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground")}>
        <Icon className="size-4" />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Label htmlFor={id} className="cursor-pointer text-sm font-semibold">{title}</Label>
          <Badge variant="outline" className="text-[10px] font-medium text-muted-foreground">{optionalLabel}</Badge>
        </div>
        <p className="mt-1 text-sm leading-5 text-muted-foreground">{description}</p>
        <p id={`${id}-detail`} className="mt-2 text-[11px] leading-4 text-muted-foreground/85">{detail}</p>
      </div>
      <Switch
        id={id}
        className="mt-1"
        checked={checked}
        disabled={disabled}
        aria-describedby={`${id}-detail`}
        onCheckedChange={onCheckedChange}
      />
    </div>
  );
}
