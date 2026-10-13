/**
 * `popover.tsx` — minimal popover primitive (Radix-free, no install).
 *
 * Why not @radix-ui/react-popover: the workspace doesn't carry it
 * (only `react-label`, `react-select`, `react-slot`, `react-tabs` are
 * in the @radix-ui set in `apps/web_admin`). A 20-line popover with
 * `position: absolute` + Escape handling + click-outside covers the
 * one usage (HU-X.8's `<BranchPickerInline />`) without pulling in a
 * new dependency.
 *
 * Single-shot: render-on-mount only (no virtual positioning, no portal
 * outside the trigger's offset parent). Adequate for the inline
 * branch picker use case where the popover sits below a header button.
 */
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface PopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger: ReactNode;
  children: ReactNode;
  /** Test id propagated to the popover panel for easier debugging. */
  testId?: string;
  /** Class name for the panel container. */
  className?: string;
  /** Alignment relative to the trigger. */
  align?: 'start' | 'end' | 'center';
}

export function Popover({
  open,
  onOpenChange,
  trigger,
  children,
  testId,
  className,
  align = 'start',
}: PopoverProps): JSX.Element {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [internalOpen, setInternalOpen] = useState(false);

  // Click outside closes the popover.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (containerRef.current?.contains(target)) return;
      onOpenChange(false);
    };
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onOpenChange(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onOpenChange]);

  // Map align to CSS alignment.
  const alignClass =
    align === 'end'
      ? 'right-0'
      : align === 'center'
        ? 'left-1/2 -translate-x-1/2'
        : 'left-0';

  return (
    <div ref={containerRef} className="relative inline-block">
      <div onClick={() => setInternalOpen(true)}>{trigger}</div>
      {(open || internalOpen) && (
        <div
          ref={panelRef}
          role="dialog"
          aria-modal="false"
          data-testid={testId}
          data-state={open ? 'open' : 'closed'}
          className={cn(
            'absolute top-full z-50 mt-1 rounded-md border border-input bg-popover text-popover-foreground shadow-md',
            alignClass,
            className,
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}
