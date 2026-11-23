// After shadcn/ui's Card and Badge (MIT, https://ui.shadcn.com).
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bg-card text-card-foreground border border-border rounded-lg", className)} {...props} />;
}

export function Badge({ className, soft, ...props }: HTMLAttributes<HTMLSpanElement> & { soft?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-px text-[11.5px] font-medium border border-border whitespace-nowrap",
        soft && "bg-secondary",
        className,
      )}
      {...props}
    />
  );
}
