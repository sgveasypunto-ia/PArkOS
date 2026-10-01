/**
 * `tabs.tsx` — accessible tabs primitive built on `@radix-ui/react-tabs`
 * (PR2 of the web_admin redesign).
 *
 * Used by the configuration surfaces (Tarifas, Cupos, Tolerancias,
 * Seguridad, Audit) to add a "Mi sucursal activa" tab alongside the
 * existing cross-branch view. The admin chooses scope per page; the
 * picker state lives in `useSucursal()` (`apps/web_admin/src/lib/sucursal-context.tsx`).
 *
 * Why shadcn-style (compound + forwardRef) instead of a wrapper:
 *   - Consumers compose `<Tabs defaultValue>` and inside it
 *     `<TabsList>`, `<TabsTrigger value="…">`, `<TabsContent value="…">`,
 *     the same shape Radix exposes. No magic prop drilling.
 *   - `TabsTrigger` renders `<button type="button">` so it never
 *     accidentally submits an enclosing `<form>` (matters inside the
 *     Tarifa/Cupo form modals where the form is the parent).
 *   - `TabsContent` is wrapped in a `<section role="tabpanel">` with the
 *     right `aria-labelledby` wired by Radix.
 *
 * WCAG: keyboard nav (Left/Right, Home/End) inherited from Radix.
 * Visual: underline-style trigger to match the rest of the chrome and
 * the macOS elevation vocabulary.
 */
import * as React from 'react';
import * as TabsPrimitive from '@radix-ui/react-tabs';

import { cn } from '@/lib/utils';

const Tabs = TabsPrimitive.Root;

const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      'border-b border-border inline-flex h-9 items-center gap-1 text-muted-foreground',
      className,
    )}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    type="button"
    className={cn(
      'focus-ring inline-flex items-center justify-center whitespace-nowrap rounded-t-md px-3 py-1.5 text-sm font-medium transition-colors duration-fast ease-macos',
      'border-b-2 border-transparent -mb-px',
      'hover:text-foreground',
      'data-[state=active]:border-primary data-[state=active]:text-foreground',
      'disabled:pointer-events-none disabled:opacity-50',
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn('mt-4 focus-ring', className)}
    {...props}
  />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsList, TabsTrigger, TabsContent };
