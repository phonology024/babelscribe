// After shadcn/ui's Switch (MIT, https://ui.shadcn.com), built on Radix UI (MIT). Gold when on.
import * as SwitchPrimitive from "@radix-ui/react-switch";
import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

export function Switch({ className, ...props }: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "relative w-9 h-5 shrink-0 rounded-full border-0 p-0 bg-input transition-colors duration-150 " +
          "data-[state=checked]:bg-gold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
          "disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className="absolute top-0.5 left-0.5 block size-4 rounded-full bg-background shadow-[0_1px_2px_rgba(0,0,0,.25)] transition-transform duration-150 data-[state=checked]:translate-x-4"
      />
    </SwitchPrimitive.Root>
  );
}
