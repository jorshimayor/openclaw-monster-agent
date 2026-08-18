"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded text-sm font-mono tracking-wider transition-all disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-matrix/60",
  {
    variants: {
      variant: {
        default:
          "bg-matrix/10 text-matrix border border-matrix/40 hover:bg-matrix/20 shadow-matrix-glow",
        ghost:
          "text-matrix border border-transparent hover:bg-matrix/10 hover:border-matrix/20",
        matrix:
          "bg-matrix/15 text-matrix border border-matrix/50 hover:bg-matrix/25 shadow-matrix-glow hover:shadow-[0_0_20px_rgba(0,255,65,0.45)]"
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-base"
      }
    },
    defaultVariants: {
      variant: "default",
      size: "md"
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size }), className)}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
