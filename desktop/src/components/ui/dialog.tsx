// After shadcn/ui's Dialog (MIT, https://ui.shadcn.com), built on Radix UI (MIT): focus trap, Esc, aria.
import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export function ConfirmDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  children: ReactNode; // the buttons
}) {
  return (
    <DialogPrimitive.Root open={props.open} onOpenChange={props.onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] animate-fade" />
        <DialogPrimitive.Content
          role="alertdialog"
          className="fixed left-1/2 top-1/2 z-50 flex w-[calc(100%-32px)] max-w-[420px] -translate-x-1/2 -translate-y-1/2 flex-col gap-3.5 rounded-lg border border-border bg-background p-6 shadow-[0_24px_60px_-24px_hsl(var(--shadow)/.5)]"
        >
          <DialogPrimitive.Title asChild>
            <h2>{props.title}</h2>
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="text-[12.5px] text-muted-foreground">
            {props.description}
          </DialogPrimitive.Description>
          <div className="flex flex-wrap items-center justify-end gap-2">{props.children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export const DialogClose = DialogPrimitive.Close;
