/**
 * `TiqueteModal.tsx` — success dialog after a successful 201 from
 * `POST /operacion/ingresos` (HU-F6.1, CU-01, T7).
 *
 * The dialog:
 *   - Shows the freshly-issued `uuid_ingreso` + the operator-visible
 *     banner (Mensualidad vs Rotación per DEC-SUC-21).
 *   - Exposes an always-on "Imprimir" button (E3 exemption, distinct
 *     from Fase 8 `reimpresion_ticket` workflow). The button calls
 *     `bridge.imprimir({ buffer, ticketId })` using the typed bridge
 *     surface from F5.1 (T0a extended `PrintPayload` with `buffer`).
 *   - Exposes a "Siguiente" button to dismiss the modal and reset the
 *     form for the next vehicle.
 *
 * i18n keys added in T9:
 *   - `tiquete_entrada_imprimir` — Imprimir button
 *   - `tiquete_entrada_siguiente` — Siguiente button
 *   - `tiquete_entrada_titulo` (reused from F6.2)
 *   - `ingreso_registrado_exitoso` (reused from F6.2)
 */
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export interface TiqueteModalProps {
  open: boolean;
  uuid_ingreso: string;
  tipo_entrada: 'MENSUALIDAD' | 'ROTACION';
  /**
   * Closure that produces a fresh `bridge.imprimir` payload for the
   * given `uuid_ingreso`. Centralised so the page can swap the
   * builder between F5.2 / F6.2 / browser-fallback without coupling
   * the modal to either.
   */
  buildPrintPayload: (uuid_ingreso: string) => {
    buffer: string;
    ticketId: string;
    cut: boolean;
  };
  /** Called when the operator clicks "Siguiente" — reset form, clear cache. */
  onSiguiente: () => void;
}

export function TiqueteModal({
  open,
  uuid_ingreso,
  tipo_entrada,
  buildPrintPayload,
  onSiguiente,
}: TiqueteModalProps) {
  const { t } = useTranslation('operacion');
  const [printing, setPrinting] = useState(false);
  const [printError, setPrintError] = useState<string | null>(null);

  const handlePrint = useCallback(async () => {
    setPrintError(null);
    setPrinting(true);
    try {
      const payload = buildPrintPayload(uuid_ingreso);
      const result = await window.bridge.imprimir(payload);
      if (!result.ok) {
        setPrintError(
          t('tiquete_entrada_print_error', {
            defaultValue:
              'No se pudo imprimir el tiquete. Puedes reintentar desde este diálogo.',
          }),
        );
      }
    } catch {
      setPrintError(
        t('tiquete_entrada_print_error', {
          defaultValue:
            'No se pudo imprimir el tiquete. Puedes reintentar desde este diálogo.',
        }),
      );
    } finally {
      setPrinting(false);
    }
  }, [buildPrintPayload, t, uuid_ingreso]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onSiguiente();
      }}
    >
      <DialogContent role="dialog" aria-describedby="tiquete-descripcion">
        <DialogHeader>
          <DialogTitle>
            {t('tiquete_entrada_titulo', {
              defaultValue: 'Tiquete de entrada',
            })}
          </DialogTitle>
          <DialogDescription id="tiquete-descripcion">
            {t('ingreso_registrado_exitoso', {
              defaultValue: 'Ingreso registrado exitosamente',
            })}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 text-sm">
          <p>
            <span className="font-medium">
              {t('tiquete_entrada_folio', { defaultValue: 'Folio' })}:
            </span>{' '}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              {uuid_ingreso}
            </code>
          </p>
          <p>
            <span className="font-medium">
              {t('ingreso_tipo_entrada_label', { defaultValue: 'Tipo' })}:
            </span>{' '}
            {tipo_entrada === 'MENSUALIDAD'
              ? t('ingreso_mensualidad_activa', {
                  defaultValue: 'Mensualidad activa',
                })
              : t('ingreso_rotacion_label', { defaultValue: 'Rotación' })}
          </p>
          {printError && (
            <p
              role="alert"
              className="text-sm text-destructive"
            >
              {printError}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handlePrint}
            disabled={printing}
            aria-label={t('tiquete_entrada_imprimir', {
              defaultValue: 'Imprimir',
            })}
          >
            {t('tiquete_entrada_imprimir', { defaultValue: 'Imprimir' })}
          </Button>
          <Button
            type="button"
            onClick={onSiguiente}
            aria-label={t('tiquete_entrada_siguiente', {
              defaultValue: 'Siguiente',
            })}
          >
            {t('tiquete_entrada_siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
