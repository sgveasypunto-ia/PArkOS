import * as React from 'react';

import { cn } from '@/lib/utils';
import { Input } from './input';
import {
  computeCaretPosition,
  formatMoneyDisplay,
  sanitizeMoneyInput,
} from '@/lib/money-input-format';

export type MoneyInputProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  'value' | 'onChange' | 'type'
> & {
  value: number | undefined;
  onChange: (rawDigits: string) => void;
  placeholder?: string;
  inputId?: string;
  inputTestId?: string;
  disabled?: boolean;
};

/**
 * `<MoneyInput />` — COP money input wrapping the shadcn `<Input>`
 * base (`components/ui/input.tsx`). Shows a live-formatted thousands
 * grouping (`50.000`) while the parent/form state stays a plain raw
 * digit string (`"50000"`, pre-transform — same shape Zod schemas in
 * this app already expect). The `$` sign is a separate decorative
 * `<span>`, never part of the formatted string itself.
 *
 * Caret handling: typing/pasting/deleting reformats the display
 * inline, so the caret has to be recomputed and reapplied after each
 * change (`computeCaretPosition`) — otherwise it would jump to the
 * end on every keystroke once grouping separators shift.
 *
 * External resync: when `value` changes from OUTSIDE while the input
 * is focused (e.g. a parent re-render mid-typing), the displayed text
 * is NOT overwritten — only unfocused external changes resync the
 * display, tracked via a ref (not state) to avoid an extra render.
 */
export const MoneyInput = React.forwardRef<HTMLInputElement, MoneyInputProps>(
  function MoneyInput(
    {
      value,
      onChange,
      placeholder,
      inputId,
      inputTestId,
      disabled,
      className,
      onFocus,
      onBlur,
      ...rest
    },
    forwardedRef,
  ) {
    const [display, setDisplay] = React.useState<string>(() =>
      formatMoneyDisplay(value !== undefined ? String(value) : ''),
    );
    const isFocusedRef = React.useRef(false);
    const innerRef = React.useRef<HTMLInputElement | null>(null);

    const setRefs = React.useCallback(
      (el: HTMLInputElement | null) => {
        innerRef.current = el;
        if (typeof forwardedRef === 'function') {
          forwardedRef(el);
        } else if (forwardedRef) {
          forwardedRef.current = el;
        }
      },
      [forwardedRef],
    );

    React.useEffect(() => {
      if (isFocusedRef.current) return;
      setDisplay(formatMoneyDisplay(value !== undefined ? String(value) : ''));
    }, [value]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
      const caretBefore = e.target.selectionStart ?? e.target.value.length;
      const digitsAfter = sanitizeMoneyInput(e.target.value);
      const newDisplay = formatMoneyDisplay(digitsAfter);
      const caretAfter = computeCaretPosition(digitsAfter, display, caretBefore);

      setDisplay(newDisplay);
      onChange(digitsAfter);

      const el = e.target;
      requestAnimationFrame(() => {
        el.setSelectionRange(caretAfter, caretAfter);
      });
    };

    const handleFocus = (e: React.FocusEvent<HTMLInputElement>): void => {
      isFocusedRef.current = true;
      onFocus?.(e);
    };

    const handleBlur = (e: React.FocusEvent<HTMLInputElement>): void => {
      isFocusedRef.current = false;
      onBlur?.(e);
    };

    return (
      <div className="relative">
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
        >
          $
        </span>
        <Input
          {...rest}
          ref={setRefs}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          id={inputId}
          data-testid={inputTestId}
          disabled={disabled}
          placeholder={placeholder}
          value={display}
          onChange={handleChange}
          onFocus={handleFocus}
          onBlur={handleBlur}
          className={cn('pl-7', className)}
        />
      </div>
    );
  },
);
MoneyInput.displayName = 'MoneyInput';
