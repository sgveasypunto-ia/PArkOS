/**
 * `FormModal.tsx` — modal base para los formularios de creación / edición
 * de los catálogos PR-D (tarifas, cupos, tipos-vehiculo, tipo-tarifa,
 * configuracion-tolerancias, configuracion-seguridad).
 *
 * Envuelve el `Dialog` ya testeado con título, descripción y slot de
 * error (server errors tipados en clases — `TarifaOverlapError`,
 * `CantidadBajoIngresosError`, `CantidadSucursalInmutableError`, etc.).
 *
 * El caller es dueño de:
 *   - el `<form onSubmit={...}>` que envuelve los fields + los buttons
 *     Cancelar / Submit, para evitar formularios anidados (HTML inválido);
 *   - la llamada a `form.handleSubmit(...)` con sus propias validaciones.
 * El FormModal solo aporta la accesibilidad del shell (title wired to
 * aria-labelledby via the Dialog component, error slot role="alert")
 * y los estilos del Card-like container.
 *
 * El children debe ser el form completo. El error slot arriba del
 * children muestra mensajes del backend.
 */
import * as React from 'react';

import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';

export interface FormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Subtitle shown under the title. Optional. */
  description?: string;
  /** Server error to surface as `role="alert"`. Optional. */
  error?: string | null;
  /**
   * The complete form (caller-owned `<form onSubmit={...}>` wrapping
   * the fields + the Cancelar / Submit buttons).
   */
  children: React.ReactNode;
  /** Spread onto the underlying Dialog `contentProps` for `data-testid`. */
  contentProps?: React.HTMLAttributes<HTMLDivElement> & {
    'data-testid'?: string;
  };
}

export function FormModal({
  open,
  onOpenChange,
  title,
  description,
  error,
  children,
  contentProps,
}: FormModalProps): JSX.Element | null {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      contentProps={contentProps}
    >
      <div className="mx-auto flex max-w-2xl flex-col gap-4 rounded-xl border bg-card p-6 shadow-elevation-2">
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

        {children}
      </div>
    </Dialog>
  );
}
