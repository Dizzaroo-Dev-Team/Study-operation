import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes safely, resolving conflicts.
 * Used by all shadcn/ui components (ISF module).
 */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
