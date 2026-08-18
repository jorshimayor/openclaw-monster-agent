import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toISOString().replace("T", " ").slice(0, 19);
}

export function truncate(s: string, n: number = 80): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 3) + "...";
}
