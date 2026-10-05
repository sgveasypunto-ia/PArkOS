/**
 * `dropdown-menu.tsx` — menu no modal anclado a un trigger, con la
 * accesibilidad que WCAG 2.1 AA exige y que un `div` con `onClick` no da:
 *  - `role="menu"` + `role="menuitem"` (lectores de pantalla anuncian el
 *    dialogo correctamente y permiten navegar entre items con flechas).
 *  - `aria-haspopup="menu"` + `aria-expanded` en el trigger.
 *  - Cierre por click-afuera, Escape, o seleccionar un item.
 *  - Restauración de foco al trigger al cerrarse.
 *  - Trap suave: Tab/Shift-Tab mueven entre items en ciclo.
 *
 * POR QUE HAND-ROLLED EN LUGAR DE `@radix-ui/react-dropdown-menu`:
 *   Mismo argumento que `dialog.tsx`. El paquete no esta en el
 *   `package.json` y agregarlo solo para este caso arrastra un
 *   `@radix-ui/react-id`, `@radix-ui/react-focus-scope`, etc. La
 *   responsabilidad del menu es pequena y la superficie a testear,
 *   pequena tambien. El patron de hand-roll con primitivos DOM + ARIA
 *   ya esta canoneado en `dialog.tsx`, asi que este archivo lo sigue.
 *
 * ANIMACION: fade-in con el `ease-macos` y `duration-fast` que ya
 * define `index.css`. Respeta `prefers-reduced-motion` via el reset
 * global.
 */
import * as React from 'react';
import { createContext, useContext, useEffect, useId, useRef, useState } from 'react';

import { cn } from '@/lib/utils';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  '[role="menuitem"]:not([aria-disabled="true"])',
].join(',');

interface DropdownContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  // Mutable on purpose: `DropdownMenuTrigger` writes `current` from a
  // callback ref. `React.RefObject<T>.current` is `readonly` under the
  // React 18 types, so the mutable variant is the correct annotation.
  triggerRef: React.MutableRefObject<HTMLButtonElement | null>;
  contentId: string;
  triggerId: string;
  labelId: string;
}

const DropdownContext = createContext<DropdownContextValue | null>(null);

function useDropdownContext(component: string): DropdownContextValue {
  const ctx = useContext(DropdownContext);
  if (!ctx) {
    throw new Error(`${component} must be rendered inside <DropdownMenu>`);
  }
  return ctx;
}

export interface DropdownMenuProps {
  children: React.ReactNode;
}

/**
 * Owns open-state side effects: click-outside, Escape, focus restoration,
 * and the keyboard cycle between menuitems.
 */
export function DropdownMenu({ children }: DropdownMenuProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const generated = useId();
  const triggerId = `dropdown-trigger-${generated}`;
  const contentId = `dropdown-content-${generated}`;
  const labelId = `dropdown-label-${generated}`;

  return (
    <DropdownContext.Provider
      value={{ open, setOpen, triggerRef, contentId, triggerId, labelId }}
    >
      {/*
        Anchoring wrapper — `position: relative` is required so the
        `DropdownMenuContent`'s `absolute top-full` lands on the trigger,
        not on the initial containing block (the viewport). Without this
        every dropdown flies to the bottom-right corner of the screen
        regardless of where the trigger is — see bug audit
        2026-10-02 (Engram #2269). `inline-flex shrink-0` keeps the
        trigger's intrinsic size inside flex parents and prevents the
        wrapper from collapsing the trigger when the parent has
        `flex-wrap` and tight space (e.g. the new admin TopNav header).
      */}
      <div className="relative inline-flex shrink-0">
        {children}
      </div>
    </DropdownContext.Provider>
  );
}

export interface DropdownMenuTriggerProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}

export const DropdownMenuTrigger = React.forwardRef<
  HTMLButtonElement,
  DropdownMenuTriggerProps
>(({ className, children, onClick, asChild: _asChild, ...props }, ref) => {
  const { open, setOpen, triggerRef, contentId, triggerId } = useDropdownContext(
    'DropdownMenuTrigger',
  );

  // The forwardRef is the SOURCE OF TRUTH for the trigger element so
  // `useEffect` in DropdownMenuContent can read it. The internal
  // `triggerRef` from context is kept in sync via a callback ref.
  const setRefs = (node: HTMLButtonElement | null): void => {
    triggerRef.current = node;
    if (typeof ref === 'function') ref(node);
    else if (ref) (ref as React.MutableRefObject<HTMLButtonElement | null>).current = node;
  };

  return (
    <button
      ref={setRefs}
      id={triggerId}
      type="button"
      aria-haspopup="menu"
      aria-expanded={open}
      aria-controls={open ? contentId : undefined}
      data-testid="dropdown-trigger"
      className={cn('focus-ring', className)}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented) setOpen(!open);
      }}
      {...props}
    >
      {children}
    </button>
  );
});
DropdownMenuTrigger.displayName = 'DropdownMenuTrigger';

export interface DropdownMenuContentProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Alignment of the content relative to the trigger. */
  align?: 'start' | 'end';
}

export const DropdownMenuContent = React.forwardRef<
  HTMLDivElement,
  DropdownMenuContentProps
>(({ className, align = 'end', ...props }, ref) => {
  const { open, setOpen, triggerRef, contentId, labelId } = useDropdownContext(
    'DropdownMenuContent',
  );
  const contentRef = useRef<HTMLDivElement | null>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const content = contentRef.current;
    if (!content) return;

    restoreFocusRef.current = document.activeElement as HTMLElement | null;

    // Focus the first non-disabled item so keyboard users land somewhere
    // usable immediately.
    const first = content.querySelectorAll<HTMLElement>(FOCUSABLE)[0];
    first?.focus();

    function onMouseDown(event: MouseEvent): void {
      const target = event.target as Node | null;
      if (!target) return;
      if (content?.contains(target)) return;
      if (triggerRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === 'Escape') {
        event.stopPropagation();
        setOpen(false);
        return;
      }
      if (event.key !== 'Tab' || !content) return;

      const items = Array.from(content.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const firstEl = items[0]!;
      const lastEl = items[items.length - 1]!;
      const active = document.activeElement;

      if (event.shiftKey && (active === firstEl || active === content)) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && active === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    }

    document.addEventListener('mousedown', onMouseDown, true);
    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('mousedown', onMouseDown, true);
      document.removeEventListener('keydown', onKeyDown, true);
      // Restore focus to the trigger (or whatever was focused before).
      // If the user clicked an item that navigated, the new page owns focus.
      const active = document.activeElement as HTMLElement | null;
      if (active === document.body) {
        restoreFocusRef.current?.focus();
      }
    };
  }, [open, setOpen, triggerRef]);

  if (!open) return null;

  const setContentRefs = (node: HTMLDivElement | null): void => {
    contentRef.current = node;
    if (typeof ref === 'function') ref(node);
    else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
  };

  return (
    <div
      ref={setContentRefs}
      id={contentId}
      role="menu"
      aria-labelledby={labelId}
      data-testid="dropdown-content"
      data-align={align}
      className={cn(
        'absolute top-full z-50 mt-1.5 min-w-[14rem] origin-top-right rounded-md border bg-background p-1',
        'shadow-elevation-3 animate-fade-in',
        align === 'end' ? 'right-0' : 'left-0',
        className,
      )}
      {...props}
    />
  );
});
DropdownMenuContent.displayName = 'DropdownMenuContent';

export interface DropdownMenuLabelProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Optional id override; if absent, an id is generated so the menu can label itself. */
  id?: string;
}

export const DropdownMenuLabel = React.forwardRef<
  HTMLDivElement,
  DropdownMenuLabelProps
>(({ className, id, ...props }, ref) => {
  const { labelId } = useDropdownContext('DropdownMenuLabel');
  return (
    <div
      ref={ref}
      id={id ?? labelId}
      className={cn('px-3 py-2 text-sm', className)}
      {...props}
    />
  );
});
DropdownMenuLabel.displayName = 'DropdownMenuLabel';

export const DropdownMenuSeparator = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    role="separator"
    aria-orientation="horizontal"
    className={cn('my-1 h-px bg-border', className)}
    {...props}
  />
));
DropdownMenuSeparator.displayName = 'DropdownMenuSeparator';

export interface DropdownMenuItemProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'disabled'> {
  /** Visually + ARIA disabled. Stays focusable so screen readers still announce it. */
  disabled?: boolean;
  destructive?: boolean;
  /**
   * Whether the menu should auto-close after the item is activated.
   * Defaults to `true` so the common case (navigate, toggle) just works.
   * Set to `false` for items that perform async work (e.g. "Cerrar
   * sesión") so the user keeps the visual feedback of the in-flight
   * state until the action finishes and the page changes.
   */
  closeOnSelect?: boolean;
}

export const DropdownMenuItem = React.forwardRef<
  HTMLButtonElement,
  DropdownMenuItemProps
>(
  (
    {
      className,
      disabled,
      destructive,
      closeOnSelect = true,
      onClick,
      children,
      ...props
    },
    ref,
  ) => {
    const { setOpen } = useDropdownContext('DropdownMenuItem');
    return (
      <button
        ref={ref}
        type="button"
        role="menuitem"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        data-testid="dropdown-item"
        onClick={(event) => {
          if (disabled) {
            event.preventDefault();
            return;
          }
          onClick?.(event);
          if (!event.defaultPrevented && closeOnSelect) setOpen(false);
        }}
        className={cn(
          'focus-ring flex w-full items-center gap-2 rounded-sm px-3 py-2 text-left text-sm transition-colors duration-fast',
          'hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground',
          disabled && 'pointer-events-none opacity-50',
          destructive && 'text-destructive hover:bg-destructive/10 hover:text-destructive',
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
DropdownMenuItem.displayName = 'DropdownMenuItem';
