/**
 * `input.tsx` — shadcn primitive for `<Input>`. Mirror of
 * `electron-sucursal/src/components/ui/input.tsx` (DEC-UI-01).
 *
 * The pattern is: forwardRef + cva-free class composition via `cn()`,
 * `aria-invalid` propagation for form validation, `disabled` styling
 * for the lockout countdown (the `<LockoutBlock />` disables the
 * whole form via the `disabled` prop on `<fieldset>` parent, so
 * every input inside needs the same disabled-state styling).
 */
import * as React from 'react';

import { cn } from '@/lib/utils';

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive',
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = 'Input';
