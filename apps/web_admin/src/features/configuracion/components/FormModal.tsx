/**
 * `FormModal.tsx` — modal base para los formularios de creación / edición
 * de los catálogos PR-D (tarifas, cupos, tipos-vehiculo, tipo-tarifa,
 * configuracion-tolerancias, configuracion-seguridad).
 *
 * Envuelve el `Dialog` ya testeado con título, descripción, slot de
 * error (server errors tipados en clases — `TarifaOverlapError`,
 * `CantidadBajoIngresosError`, `CantidadSucursalInmutableError`, etc.),
 * slot de children (el form concreto), y un footer con botones
 * Cancelar + Submit.
 *
 * El `submitLabel` cambia entre "Crear" y "Actualizar" según el
 * caller. El estado `submitting` deshabilita ambos botones para
 * evitar double-submit. El `error` se renderiza como `role="alert"`
 * con `aria-live="assertive"` para que un screen reader lo anuncie.
 *
 * NO incluye form logic ni Zod schema — eso vive en cada feature
 * concreta (TarifaForm, CupoForm, etc.). El FormModal solo da el
 * shell de presentación y la accesibilidad.
 */
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';

import { cn } from '@/lib/utils';

export interface FormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Subtitle shown under the title. Optional. */
  description?: string;
  submitLabel: string;
  submitting: boolean;
  /** Server error to surface as `role="alert"`. Optional. */
  error?: string | null;
  /**
   * The form fields. Caller is responsible for `<form onSubmit={...}>`
   * and field-level labels/validation; FormModal only owns the shell.
   */
  children: React.ReactNode;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  /** Spread onto the underlying Dialog `contentProps` for `data-testid`. */
  contentProps?: React.HTMLAttributes<HTMLDivElement>;
}

export function FormModal({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  submitting,
  error,
  children,
  onSubmit,
  contentProps,
}: FormModalProps): JSX.Element | null {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      contentProps={contentProps}
    >
      <form
        onSubmit={onSubmit}
        className="mx-auto flex max-w-2xl flex-col gap-4 rounded-xl border bg-card p-6 shadow-elevation-2"
      >
        <div className="flex flex-col gap-1">
          <DialogTitle>{title}</DialogTitle>
          {description !== undefined && (
            <DialogDescription>{description}</DialogDescription>
          )}
        </div>

        {error !== undefined && error !== null && (
          <p
            role="alert"
            aria-live="assertive"
            data-testid="form-modal-error"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <div className="flex flex-col gap-3">{children}</div>

        <div className="mt-2 flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
            data-testid="form-modal-cancel"
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={submitting}
            data-testid="form-modal-submit"
            className={cn(submitting && 'opacity-70')}
          >
            {submitting ? `${submitLabel}…` : submitLabel}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
