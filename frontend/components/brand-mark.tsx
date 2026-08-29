import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-9 rotate-[-3deg] items-center justify-center rounded-xl bg-primary text-xs font-black tracking-[-0.08em] text-primary-foreground shadow-[0_5px_0_#9b1026]",
        className,
      )}
      aria-hidden
    >
      DV
    </span>
  );
}
