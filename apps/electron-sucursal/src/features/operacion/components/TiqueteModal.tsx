/**
 * `TiqueteModal.tsx` — success dialog after a successful 201 from
 * `POST /operacion/ingresos` (HU-F6.1, CU-01, T7; HU-INGRESO-SIN-PLACA
 * REQ-OPS-197 — render `Identificación:` for no-placa ingresos).
 *
 * The dialog:
 *   - Shows a PRINT PREVIEW thumbnail (the layout the printer will
 *     emit, rendered as an HTML block) so the operator can verify
 *     what they're about to print before pressing "Imprimir" — REGRESSION
 *     fix (2026-09-22): previously the modal only echoed the metadata
 *     fields and went straight to ``bridge.imprimir`` on click, which
 *     left the operator blind to layout problems (e.g. truncation,
 *     missing fields). The preview is intentionally monospace + bordered
 *     to mirror the 58 mm thermal-printer aesthetic (see DEC-SUC-26).
 *   - Shows the freshly-issued `uuid_ingreso` + the operator-visible
 *     banner (Mensualidad vs Rotación per DEC-SUC-21).
 *   - For no-placa ingresos (consecutivo present), renders an
 *     `Identificación: {consecutivo}` line INSTEAD of the legacy
 *     placa display (operator-facing label per DEC-SUC-26 + Q3).
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
 *   - `tiquete_identificacion_label` — "Identificación" (HU-INGRESO-SIN-PLACA)
 *   - `tiquete_entrada_preview_header` — "Tiquete de entrada" (the
 *     preview's centered header line, distinct from the modal title)
 *   - `tiquete_entrada_preview_fecha` — "Fecha:" (preview field label)
 *   - `tiquete_entrada_preview_tipo` — "Tipo:" (preview field label)
 *   - `tiquete_entrada_preview_id` — "Identificación:" (preview field label)
 *   - `tiquete_entrada_preview_folio` — "Folio:" (preview field label)
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
   * REQ-OPS-197: parking-lot identifier for no-placa ingresos.
   * When non-null, the modal renders `Identificación: {consecutivo}`
   * instead of any placa display. Null for legacy carro/moto rows
   * (REQ-OPS-192 backward compat).
   */
  consecutivo?: string | null;
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
  consecutivo,
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

        {/* REGRESSION fix (2026-09-22): render a print-preview thumbnail so
            the operator sees the layout that will be emitted to the
            58 mm thermal printer before pressing "Imprimir". The
            preview mirrors the escposBuilder template (F5.2):
            monospace + 58 mm-ish width + dashed border + centered
            header. The same ``consecutivo`` / ``uuid_ingreso`` /
            ``tipo_entrada`` fields shown in the metadata block below
            are also drawn in the preview so the operator can spot
            layout problems (truncation, missing fields) BEFORE the
            print job goes to the printer. */}
        <div
          data-testid="tiquete-preview"
          aria-label={t('tiquete_entrada_preview_header', {
            defaultValue: 'Tiquete de entrada',
          })}
          className="mx-auto w-full max-w-sm rounded border border-dashed border-muted-foreground/40 bg-white p-3 font-mono text-xs leading-relaxed text-neutral-900 shadow-inner"
        >
          <div className="mb-2 text-center font-bold uppercase tracking-wide">
            {t('tiquete_entrada_preview_header', {
              defaultValue: 'Tiquete de entrada',
            })}
          </div>
          <div className="border-t border-dashed border-neutral-400 pt-1">
            <div>
              <span className="font-semibold">
                {t('tiquete_entrada_preview_fecha', { defaultValue: 'Fecha:' })}
              </span>{' '}
              {new Date().toLocaleString('es-CO', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
              })}
            </div>
            <div>
              <span className="font-semibold">
                {t('tiquete_entrada_preview_tipo', { defaultValue: 'Tipo:' })}
              </span>{' '}
              {tipo_entrada === 'MENSUALIDAD'
                ? t('ingreso_mensualidad_activa', {
                    defaultValue: 'Mensualidad',
                  })
                : t('ingreso_rotacion_label', { defaultValue: 'Rotación' })}
            </div>
            <div>
              <span className="font-semibold">
                {t('tiquete_entrada_preview_id', {
                  defaultValue: 'Identificación:',
                })}
              </span>{' '}
              {consecutivo !== null && consecutivo !== undefined ? (
                consecutivo
              ) : (
                <span className="text-neutral-500">—</span>
              )}
            </div>
            <div>
              <span className="font-semibold">
                {t('tiquete_entrada_preview_folio', { defaultValue: 'Folio:' })}
              </span>{' '}
              <span className="break-all">{uuid_ingreso}</span>
            </div>
          </div>
        </div>

        <div className="space-y-2 text-sm">
          {/* REQ-OPS-197 — `Identificación:` replaces the placa display
              for no-placa ingresos. Null for legacy carro/moto. */}
          {consecutivo !== null && consecutivo !== undefined && (
            <p data-testid="tiquete-identificacion">
              <span className="font-medium">
                {t('tiquete_identificacion_label', {
                  defaultValue: 'Identificación',
                })}
                :
              </span>{' '}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                {consecutivo}
              </code>
            </p>
          )}
          {/* Folio always rendered for QR + audit (DEC-SUC-26). */}
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
