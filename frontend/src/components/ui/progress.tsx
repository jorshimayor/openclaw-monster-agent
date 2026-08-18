"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value: number;
}

export const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value, ...props }, ref) => {
    const pct = Math.max(0, Math.min(100, value));
    return (
      <div
        ref={ref}
        className={cn(
          "relative w-full h-2 rounded-full bg-bg-border overflow-hidden",
          className
        )}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        {...props}
      >
        <div
          className="h-full bg-matrix shadow-matrix-glow transition-all duration-500 ease-out relative"
          style={{ width: `${pct}%` }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-transparent via-matrix/40 to-transparent animate-pulse" />
        </div>
      </div>
    );
  }
);
Progress.displayName = "Progress";
