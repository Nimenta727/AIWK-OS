/**
 * Adapted from T3 Code components/ui/skeleton.tsx (MIT, T3 Tools Inc., 2026).
 * Original cva/cn and Tailwind dependencies replaced with AIWS component styles.
 */
import type { HTMLAttributes } from 'react';
export function T3Skeleton({className='',...props}:HTMLAttributes<HTMLDivElement>) {
  return <div className={`aiws-skeleton ${className}`} data-slot="skeleton" {...props}/>;
}
