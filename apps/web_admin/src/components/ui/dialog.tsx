/**
 * `dialog.tsx` — modal dialog with the four behaviours WCAG 2.1 AA
 * actually requires and that a bare `role="dialog"` div does not give you:
 * Escape to dismiss, a focus trap, `aria-modal`, and focus restoration.
 *
 * Why hand-rolled instead of Radix `<Dialog>`: `@radix-ui/react-dialog` is
 * not in this app's dependency set, and the native `<dialog>` element is
 * not an option either because jsdom 25 exposes neither `showModal()` nor
 * `close()`, so a native implementation could not be tested here at all --
 * an accessibility-critical primitive with untestable behaviour is worse
 * than no primitive. `PairingTokenDialog` already shipped a dialog whose
 * docblock claimed "Escape closes the dialog (Radix Dialog built-in)"
 * while having no key handler, no trap and no `aria-modal`; this is that
 * gap closed, with the behaviour under test.
 *
 * The animation uses the macOS curve from `index.css` (`--ease-macos`) and
 * the elevation scale, so dialogs sit above the page instead of on it.
 */
import * as React from 'react';
import { forwardRef } from 'react';

import { cn } from '@/lib/utils';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * Focusable descendants, in DOM order.
 *
 * Visibility is decided from attributes rather than layout. The usual
 * `offsetParent !== null` test is wrong here: jsdom runs no layout engine
 * and reports `null` for every element, so that filter would empty the list
 * and silently disable both the initial focus and the Tab trap -- the trap
 * would have looked implemented while doing nothing.
 */
function focusableWithin(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE),
  ).filter((el) => !el.closest('[hidden]') && el.getAttribute('aria-hidden') !== 'true');
}

interface DialogContextValue {
  titleId: string;
  descriptionId: string;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialogIds(): DialogContextValue {
  const generated = React.useId();
  return {
    titleId: `dialog-title-${generated}`,
    descriptionId: `dialog-description-${generated}`,
  };
}

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Extra class on the backdrop/positioning wrapper. */
  className?: string;
  /**
   * Spread onto the `role="dialog"` element, so a consumer can attach its
   * own `data-testid` / `data-*` hooks without the ids drifting from the
   * generated `aria-labelledby` wiring.
   */
  contentProps?: React.HTMLAttributes<HTMLDivElement>;
  children: React.ReactNode;
}

/** Owns open-state side effects: Escape, focus trap, scroll lock, focus restore. */
export function Dialog({
  open,
  onOpenChange,
  className,
  contentProps,
  children,
}: DialogProps) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const restoreFocusRef = React.useRef<HTMLElement | null>(null);
  const ids = useDialogIds();

  React.useEffect(() => {
    if (!open) return;
    const content = contentRef.current;
    if (!content) return;

    restoreFocusRef.current = document.activeElement as HTMLElement | null;

    // Move focus in, preferring the first real control over the container.
    const first = focusableWithin(content)[0] ?? content;
    first.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onOpenChange(false);
        return;
      }
      if (event.key !== 'Tab') return;

      const current = contentRef.current;
      if (!current) return;
      const focusable = focusableWithin(current);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const firstEl = focusable[0]!;
      const lastEl = focusable[focusable.length - 1]!;
      const active = document.activeElement;

      // Wrap at both ends so Tab can never reach the page behind.
      if (event.shiftKey && (active === firstEl || active === current)) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && active === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      restoreFocusRef.current?.focus();
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <DialogContext.Provider value={ids}>
      <div
        className={cn(
          'fixed inset-0 z-50 flex items-center justify-center bg-foreground/30 p-4',
          'animate-fade-in duration-base',
          className,
        )}
        // The backdrop is decorative; a click outside dismisses, matching
        // macOS sheets, but Escape and the close button remain the
        // keyboard-reachable paths so dismissal never depends on a mouse.
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onOpenChange(false);
        }}
      >
        <div
          ref={contentRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={ids.titleId}
          aria-describedby={ids.descriptionId}
          tabIndex={-1}
          className="w-full outline-none animate-scale-in duration-base"
          {...contentProps}
        >
          {children}
        </div>
      </div>
    </DialogContext.Provider>
  );
}

/** Pulls the generated ids so titles/descriptions stay wired automatically. */
function useDialogIdsFromContext(): DialogContextValue {
  const context = React.useContext(DialogContext);
  if (!context) {
    throw new Error('Dialog subcomponents must be rendered inside <Dialog>');
  }
  return context;
}

/**
 * Heading bound to the dialog's `aria-labelledby`. Call `useId` here and the
 * id would be a fresh one, so the dialog would point at nothing.
 */
export const DialogTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => {
  const { titleId } = useDialogIdsFromContext();
  return (
    <h2
      ref={ref}
      id={titleId}
      className={cn('text-lg font-semibold tracking-tight', className)}
      {...props}
    />
  );
});
DialogTitle.displayName = 'DialogTitle';

export const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => {
  const { descriptionId } = useDialogIdsFromContext();
  return (
    <p
      ref={ref}
      id={descriptionId}
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
});
DialogDescription.displayName = 'DialogDescription';

/**
 * Presentational shell for the dialog body. Plain `<div>` — no ARIA
 * wiring here, the parent `<Dialog>` already owns `role="dialog"`,
 * `aria-modal`, `aria-labelledby`, `aria-describedby`, the focus trap
 * and the Escape handler. Children are rendered verbatim.
 *
 * `forwardRef` so consumers can attach `data-testid` directly on
 * the content element when needed (e.g. `nueva-version-dialog`).
 */
export const DialogContent = forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'rounded-lg border bg-background p-6 shadow-elevation-3',
      'grid gap-4',
      className,
    )}
    {...props}
  />
));
DialogContent.displayName = 'DialogContent';

/**
 * Header block — vertical stack for `DialogTitle` + `DialogDescription`
 * with the spacing the design system uses for the upper margin of the
 * dialog. Plain `<div>`, no ARIA.
 */
export const DialogHeader = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>): JSX.Element => (
  <div
    className={cn('flex flex-col gap-1.5 text-left', className)}
    {...props}
  />
);
DialogHeader.displayName = 'DialogHeader';

/**
 * Footer block — action buttons. Stacks vertically on mobile and
 * right-aligns horizontally on `sm+`, matching the rest of the
 * app's button layouts.
 */
export const DialogFooter = ({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>): JSX.Element => (
  <div
    className={cn(
      'flex flex-col-reverse gap-2 sm:flex-row sm:justify-end',
      className,
    )}
    {...props}
  />
);
DialogFooter.displayName = 'DialogFooter';
