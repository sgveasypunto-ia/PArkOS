import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';

import { cn } from '@/lib/utils';

/**
 * Card shadcn primitive (F3.3 — T4).
 *
 * F2.1 NO shipping card.tsx (14 componentes baseline). F3.3 necesita
 * `<Card>` para `<TurnoActivoPanel>` organism (REQ-OPS-121).
 *
 * Implementación verbatim shadcn/ui Card — headings semánticos via
 * `<CardTitle>` mapea a `<h3>` (no `<div>`) para axe-core WCAG 2.1 AA
 * (REQ-OPS-124 S5).
 *
 * F11.2 fix-up: `<CardTitle>` y `<CardDescription>` aceptan `asChild`
 * (patrón shadcn) — cuando se pasa, el componente se funde con su child
 * vía `@radix-ui/react-slot`'s `<Slot>`. Esto permite a callers como
 * `<LoginForm>` usar `<CardTitle asChild><h1>…</h1></CardTitle>` para
 * preservar la jerarquía semántica de headings (sin esto, un `<h1>`
 * terminaba anidado dentro de un `<h3>` y disparaba validateDOMNesting
 * de React). Mismo patrón que `<Button asChild>` en `button.tsx`.
 */
const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'rounded-2xl border border-border/60 bg-card text-card-foreground shadow-apple-sm',
      className,
    )}
    {...props}
  />
));
Card.displayName = 'Card';

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1 px-5 pt-5 pb-3', className)}
    {...props}
  />
));
CardHeader.displayName = 'CardHeader';

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement> & { asChild?: boolean }
>(({ className, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : 'h3';
  return (
    <Comp
      ref={ref}
      className={cn(
        'text-lg font-semibold leading-none tracking-tight',
        className,
      )}
      {...props}
    />
  );
});
CardTitle.displayName = 'CardTitle';

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement> & { asChild?: boolean }
>(({ className, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : 'p';
  return (
    <Comp
      ref={ref}
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  );
});
CardDescription.displayName = 'CardDescription';

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn('px-5 pb-5', className)} {...props} />
));
CardContent.displayName = 'CardContent';

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex items-center px-5 pb-5', className)}
    {...props}
  />
));
CardFooter.displayName = 'CardFooter';

export { Card, CardHeader, CardFooter, CardTitle, CardDescription, CardContent };