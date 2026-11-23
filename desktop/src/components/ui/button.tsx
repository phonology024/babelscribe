// After shadcn/ui's Button (MIT, https://ui.shadcn.com), with the sizes and colours of the babelscribe mockup.
import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-md border border-transparent text-[13.5px] " +
    "font-medium whitespace-nowrap transition-[background-color,opacity] duration-150 " +
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
    "disabled:opacity-50 disabled:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-primary-hover",
        outline: "bg-background border-input hover:bg-accent",
        ghost: "bg-transparent hover:bg-accent",
        destructive: "bg-destructive text-destructive-foreground",
      },
      size: {
        default: "",
        sm: "h-8 px-2.5 text-[12.5px]",
        icon: "w-9 px-0",
      },
    },
    defaultVariants: { variant: "outline", size: "default" },
  },
);

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
