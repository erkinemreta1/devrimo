import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg bg-primary text-xs font-bold tracking-tight text-primary-foreground",
        className,
      )}
      aria-hidden
    >
      D
    </span>
  );
}
