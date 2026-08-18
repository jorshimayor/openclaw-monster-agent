import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-mono tracking-widest transition-colors",
  {
    variants: {
      variant: {
        default: "bg-matrix/10 text-matrix border-matrix/40",
        success: "bg-green-900/30 text-green-400 border-green-500/40",
        warning: "bg-yellow-900/30 text-yellow-400 border-yellow-500/40",
        error: "bg-red-900/30 text-red-400 border-red-500/40"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
