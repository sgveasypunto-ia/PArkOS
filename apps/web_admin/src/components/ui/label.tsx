/**
 * `label.tsx` — shadcn primitive for `<Label>` (DEC-UI-01 mirror of
 * `electron-sucursal/src/components/ui/label.tsx`).
 *
 * Uses `@radix-ui/react-label` for proper `htmlFor` association and
 * peer-input styling hooks (the `peer-disabled` modifier styles labels
 * when their sibling input is disabled — used by the lockout
 * countdown to dim the labels alongside the disabled inputs).
 *
 * Peer-dependency: `web_admin` does NOT currently declare
 * `@radix-ui/react-label` directly. It IS a transitive dep of
 * `@radix-ui/react-select` which we already depend on. Vite/TypeScript
 * resolve it through hoisting; if a future refactor breaks the
 * transitive resolution, add `@radix-ui/react-label` as an explicit
 * dep.
 */
import * as React from 'react';
import * as LabelPrimitive from '@radix-ui/react-label';
import { cva, type VariantProps } from 'class-variance-authority';

import { cn } from '@/lib/utils';

const labelVariants = cva(
  'text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70',
);

export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;
