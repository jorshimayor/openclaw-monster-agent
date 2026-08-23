import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-mono tracking-widest transition-colors",
  {
    variants: {
      variant: {
        default: "bg-matrix/10 text-matrix border-matrix/40",
        success:
          "bg-success/20 text-success border-success/50",
        warning:
          "bg-warning/20 text-warning border-warning/50",
        error:
          "bg-danger/20 text-danger border-danger/50"
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
