/**
 * `TiqueteModal.tsx` — success dialog after a successful 201 from
 * `POST /operacion/ingresos` (HU-F6.1, CU-01, T7; HU-INGRESO-SIN-PLACA
 * REQ-OPS-197 — render `Identificación:` for no-placa ingresos).
 *
 * The dialog now bundles FOUR operator-facing features (REGRESSION
 * fix chain 2026-09-22):
 *
 *   A. **Editable observaciones post-POST** — a textarea + "Guardar"
 *      button that lets the operator amend the observaciones after seeing
 *      the preview, BEFORE printing. Today this is client-side only
 *      (the backend has no PATCH /ingresos/{uuid} endpoint — the [L-E]
 *      table is insert-only per REQ-30/33). Follow-up: backend endpoint
 *      + audit log of the change.
 *   B. **Subscription-validity gate on print** — when the ingreso
 *      carries ``uuid_subscripcion_cliente``, the preview fetches the
 *      subscription row + computes ``suscripcionVigente``. When the
 *      subscription is expired (``fecha_vencimiento < today`` OR
 *      ``estado !== 'activo'`` OR ``vigente_hasta IS NOT NULL``) the
 *      "Imprimir" button is disabled and a warning block renders above
 *      the preview. The operator MUST renew the subscription or
 *      override via a separate flow (out of scope here).
 *   C. **Expanded cliente info** — the preview shows plan FK (resolved
 *      by future fetch — currently shows "Plan: <uuid>"), the
 *      ``fecha_vencimiento`` and the cliente block. Follow-up: add a
 *      ``GET /clientes/tipo-subscripciones/{uuid}`` to resolve the plan
 *      name (today we only show the FK).
 *   D. **Workflow buttons post-success** — when the operator is done
 *      with the tiquete they can either reset the form ("Siguiente",
 *      the default) or jump to the next workflow step in the
 *      operator's day: "Ir a salida" (navigates to /operacion/salida),
 *      "Anular ingreso" (TODO — opens the future anulaciones modal),
 *      "Hacer arqueo" (TODO — opens the future arqueo modal). For now
 *      only "Ir a salida" is wired; the other two are stubbed with a
 *      TODO comment + console log.
 *   F. **Auto-reset post-print** — clicking "Imprimir" now closes the
 *      dialog AND fires ``onSiguiente`` on success (the
 *      ``bridge.imprimir`` call returned ``ok: true``). The operator
 *      no longer needs to click "Siguiente" after every print — saves
 *      one click per ingreso in high-volume.
 *
 * The dialog:
 *   - Shows a PRINT PREVIEW thumbnail (the layout the printer will
 *     emit, rendered as an HTML block) so the operator can verify
 *     what they're about to print before pressing "Imprimir".
 *   - Shows the freshly-issued `uuid_ingreso` + the operator-visible
 *     banner (Mensualidad vs Rotación per DEC-SUC-21).
 *   - For no-placa ingresos (consecutivo present), renders an
 *     `Identificación: {consecutivo}` line INSTEAD of the legacy
 *     placa display (operator-facing label per DEC-SUC-26 + Q3).
 *   - For con-placa ingresos, renders the placa line in the preview.
 *   - When the ingreso has ``uuid_subscripcion_cliente``, the preview
 *     surfaces the cliente block (nombre + apellido + identificador)
 *     + a ``*** PAGO CON MENSUALIDAD ***`` sello (DEC-SUC-21).
 *   - Subscription validity gate (FEATURE B): when
 *     ``suscripcionVigente === false``, the print button is disabled.
 *   - Editable observaciones (FEATURE A): textarea + "Guardar" button.
 *   - Post-success workflow buttons (FEATURE D): Siguiente (default),
 *     Ir a salida (wired), Anular (stub), Hacer arqueo (stub).
 *
 * i18n keys added in T9 + 2026-09-22:
 *   - `tiquete_entrada_imprimir` — Imprimir button
 *   - `tiquete_entrada_siguiente` — Siguiente button (F: also auto-fired)
 *   - `tiquete_entrada_titulo` (reused from F6.2)
 *   - `ingreso_registrado_exitoso` (reused from F6.2)
 *   - `tiquete_identificacion_label` — "Identificación" (HU-INGRESO-SIN-PLACA)
 *   - `tiquete_entrada_preview_header` — "Tiquete de entrada"
 *   - `tiquete_entrada_preview_fecha` — "Fecha:"
 *   - `tiquete_entrada_preview_tipo` — "Tipo:"
 *   - `tiquete_entrada_preview_placa` — "Placa:"
 *   - `tiquete_entrada_preview_id` — "Identificación:"
 *   - `tiquete_entrada_preview_folio` — "Folio:"
 *   - `tiquete_entrada_preview_cliente` — "Cliente:"
 *   - `tiquete_entrada_preview_mensualidad_sello` — "*** Pago con mensualidad ***"
 *   - `tiquete_entrada_preview_plan_fk` — "Plan:"
 *   - `tiquete_entrada_preview_fecha_vence` — "Vence:"
 *   - `tiquete_entrada_observaciones_label` — "Observaciones:"
 *   - `tiquete_entrada_observaciones_placeholder` — placeholder text
 *   - `tiquete_entrada_observaciones_guardar` — "Guardar" button
 *   - `tiquete_entrada_observaciones_guardado` — saved confirmation
 *   - `tiquete_entrada_suscripcion_vencida` — expired-subscription warning
 *   - `tiquete_entrada_suscripcion_vencida_imprimir_bloqueado` —
 *     "No se puede imprimir: suscripción vencida."
 *   - `tiquete_entrada_ir_a_salida` — "Ir a salida"
 *   - `tiquete_entrada_anular` — "Anular"
 *   - `tiquete_entrada_arqueo` — "Hacer arqueo"
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { formatFechaHoraCorta } from '../../caja/lib/format';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { ClienteContext } from '@/features/operacion/api/clienteApi';

// shadcn/ui doesn't ship a Textarea primitive in this codebase —
// use the native HTML element with shadcn-friendly Tailwind classes
// (same pattern as the existing `id="principal-observaciones"`
// textarea in `pages/Principal.tsx`).
const TextareaNative = (
  props: React.TextareaHTMLAttributes<HTMLTextAreaElement>,
) => <textarea {...props} />;

export interface TiqueteModalProps {
  open: boolean;
  uuid_ingreso: string;
  tipo_entrada: 'MENSUALIDAD' | 'ROTACION';
  /**
   * HU-F11.x (REQ-OPS-200): concrete vehicle type name
   * (``carro`` / ``moto`` / ``bicicleta`` / ``patineta``) resolved by
   * the parent. Distinct from ``tipo_entrada`` which is just the
   * ``ROTACION`` / ``MENSUALIDAD`` discriminator. Rendered in the
   * preview so the operator sees the actual tipo they committed
   * (auto-detected OR override-selected) — useful when the regex
   * detected one thing and the operator chose another.
   */
  tipo_vehiculo_nombre?: string | null;
  /**
   * REQ-OPS-197: parking-lot identifier for no-placa ingresos.
   * When non-null, the modal renders `Identificación: {consecutivo}`
   * instead of any placa display. Null for legacy carro/moto rows
   * (REQ-OPS-192 backward compat).
   */
  consecutivo?: string | null;
  /**
   * REGRESSION fix (2026-09-22): the placa for legacy carro/moto
   * ingresos (F6.2 path). Null for no-placa ingresos. Rendered in the
   * preview when present so the operator can verify the placa before
   * printing.
   */
  placa?: string | null;
  /**
   * Cliente metadata for ingresos with ``uuid_subscripcion_cliente``
   * (i.e. tipo_entrada === 'MENSUALIDAD'). When provided, the preview
   * adds a ``Cliente: <nombre> <apellido>`` line + a
   * ``*** PAGO CON MENSUALIDAD ***`` sello (DEC-SUC-21). Hydrated by
   * the parent via ``useClienteBySubscripcion``. Also drives FEATURE B
   * (subscription-validity gate).
   */
  cliente?: ClienteContext | null;
  /**
   * Optional initial observaciones (from the form the operator filled
   * out before submitting). FEATURE A lets the operator amend this in
   * the modal; the amendment is client-side only (TODO backend).
   */
  initialObservaciones?: string;
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
  /**
   * FEATURE D: optional navigation callback for the "Ir a salida"
   * button. When provided, the button renders; otherwise it's hidden.
   */
  onIrASalida?: () => void;
}

export function TiqueteModal({
  open,
  uuid_ingreso,
  tipo_entrada,
  tipo_vehiculo_nombre = null,
  consecutivo,
  placa = null,
  cliente = null,
  initialObservaciones = '',
  buildPrintPayload,
  onSiguiente,
  onIrASalida,
}: TiqueteModalProps) {
  const { t } = useTranslation('operacion');
  const [printing, setPrinting] = useState(false);
  const [printError, setPrintError] = useState<string | null>(null);
  // FEATURE A: editable observaciones (client-side state for now).
  const [observaciones, setObservaciones] = useState(initialObservaciones);
  const [observacionesSaved, setObservacionesSaved] = useState(false);
  // FEATURE F: auto-reset after successful print. Tracked so the
  // dialog can show a "Imprimiendo…" state until close fires.

  // Reset observaciones-saved flag when dialog re-opens with a new ingreso.
  useEffect(() => {
    if (open) {
      setObservaciones(initialObservaciones);
      setObservacionesSaved(false);
      setPrintError(null);
    }
  }, [open, initialObservaciones]);

  const handlePrint = useCallback(async () => {
    setPrintError(null);
    setObservacionesSaved(false);
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
        return;
      }
      // FEATURE F: auto-reset on successful print. The operator no
      // longer needs to click "Siguiente" after every print — saves
      // one click per ingreso in high-volume. We call onSiguiente
      // synchronously to reset the parent form; the Dialog's
      // onOpenChange handler will also fire on close, but the parent
      // already cleared its state by then.
      onSiguiente();
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
  }, [buildPrintPayload, t, uuid_ingreso, onSiguiente]);

  // FEATURE B: subscription-validity gate. Compute once per render
  // (cliente is a prop, doesn't change inside the modal's lifetime).
  const subscriptionExpired =
    cliente !== null && cliente.suscripcionVigente === false;
  const canPrint = !subscriptionExpired && !printing;

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

        {/* FEATURE B: subscription-validity warning. Rendered above the
            preview so the operator notices BEFORE looking at the
            preview content. Disabled print button is the action side. */}
        {subscriptionExpired && (
          <div
            role="alert"
            data-testid="tiquete-suscripcion-vencida"
            className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
          >
            <p className="font-semibold">
              {t('tiquete_entrada_suscripcion_vencida', {
                defaultValue: 'La suscripción de este cliente está vencida.',
              })}
            </p>
            <p className="mt-1 text-xs">
              {cliente?.fechaVencimiento
                ? t('tiquete_entrada_suscripcion_vencida_imprimir_bloqueado', {
                    defaultValue:
                      'No se puede imprimir: suscripción vencida el {{fecha}}.',
                  }).replace('{{fecha}}', cliente.fechaVencimiento)
                : t('tiquete_entrada_suscripcion_vencida_imprimir_bloqueado', {
                    defaultValue: 'No se puede imprimir: suscripción vencida.',
                  })}
            </p>
          </div>
        )}

        {/* REGRESSION fix (2026-09-22): render a print-preview thumbnail so
            the operator sees the layout that will be emitted to the
            58 mm thermal printer before pressing "Imprimir". */}
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
              {formatFechaHoraCorta(new Date().toISOString())}
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
            {/*
              HU-F11.x (REQ-OPS-200): concrete vehicle type name the
              operator actually committed (resolved at submit time
              from the override UUID or the regex-detected tipo).
              Renders ABOVE the ``Tipo:`` discriminator line so the
              operator can verify both at a glance (the ``Tipo:``
              line is the commercial modality; the ``Vehículo:`` line
              is the physical class). Hidden if the parent could not
              resolve the name (defensive — the API doesn't carry it).
            */}
            {tipo_vehiculo_nombre !== null && tipo_vehiculo_nombre !== undefined && (
              <div>
                <span className="font-semibold">
                  {t('tiquete_entrada_preview_vehiculo', {
                    defaultValue: 'Vehículo:',
                  })}
                </span>{' '}
                {tipo_vehiculo_nombre}
              </div>
            )}
            {placa !== null && placa !== undefined && (
              <div>
                <span className="font-semibold">
                  {t('tiquete_entrada_preview_placa', {
                    defaultValue: 'Placa:',
                  })}
                </span>{' '}
                {placa}
              </div>
            )}
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
            {/* FEATURE C: expanded cliente block with subscription
                coverage + plan FK. Hidden entirely when no cliente
                metadata is available. */}
            {cliente !== null && (
              <>
                <div>
                  <span className="font-semibold">
                    {t('tiquete_entrada_preview_cliente', {
                      defaultValue: 'Cliente:',
                    })}
                  </span>{' '}
                  {cliente.nombre} {cliente.apellido}
                </div>
                <div>
                  <span className="font-semibold">
                    {cliente.tipoIdentificador}:
                  </span>{' '}
                  {cliente.numeroIdentificacion}
                </div>
                {cliente.fechaVencimiento && (
                  <div>
                    <span className="font-semibold">
                      {t('tiquete_entrada_preview_fecha_vence', {
                        defaultValue: 'Vence:',
                      })}
                    </span>{' '}
                    {cliente.fechaVencimiento}
                  </div>
                )}
                {cliente.uuidTipoSubscripcion && (
                  <div className="text-neutral-500">
                    <span className="font-semibold">
                      {t('tiquete_entrada_preview_plan_fk', {
                        defaultValue: 'Plan:',
                      })}
                    </span>{' '}
                    <span className="break-all text-[10px]">
                      {cliente.uuidTipoSubscripcion.slice(0, 8)}…
                    </span>
                  </div>
                )}
              </>
            )}
            <div>
              <span className="font-semibold">
                {t('tiquete_entrada_preview_folio', { defaultValue: 'Folio:' })}
              </span>{' '}
              <span className="break-all">{uuid_ingreso}</span>
            </div>
          </div>
          {cliente !== null && (
            <div className="mt-2 border-t border-dashed border-neutral-400 pt-2 text-center font-bold uppercase">
              {t('tiquete_entrada_preview_mensualidad_sello', {
                defaultValue: '*** Pago con mensualidad ***',
              })}
            </div>
          )}
        </div>

        {/* FEATURE A: editable observaciones post-POST. RHF-free —
            textarea + save button. State is local (TODO backend PATCH). */}
        <div className="space-y-2">
          <label
            htmlFor="tiquete-observaciones"
            className="text-sm font-medium"
          >
            {t('tiquete_entrada_observaciones_label', {
              defaultValue: 'Observaciones:',
            })}
          </label>
          <TextareaNative
            id="tiquete-observaciones"
            data-testid="tiquete-observaciones"
            value={observaciones}
            onChange={(e) => {
              setObservaciones(e.target.value.slice(0, 500));
              setObservacionesSaved(false);
            }}
            placeholder={t('tiquete_entrada_observaciones_placeholder', {
              defaultValue:
                'Notas adicionales del operador (opcional, máx. 500 chars)',
            })}
            maxLength={500}
            rows={2}
            className="block w-full resize-none rounded border border-input bg-background px-3 py-2 text-sm outline-none ring-ring placeholder:text-muted-foreground focus:ring-2"
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">
              {observaciones.length}/500
            </span>
            <div className="flex items-center gap-2">
              {observacionesSaved && (
                <span
                  className="text-xs text-emerald-700"
                  data-testid="tiquete-observaciones-saved"
                >
                  {t('tiquete_entrada_observaciones_guardado', {
                    defaultValue: 'Guardado (local, pendiente backend)',
                  })}
                </span>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  // TODO: wire to backend PATCH /ingresos/{uuid} when the
                  // endpoint exists. Today this is local-only — the
                  // edited value is preserved while the dialog stays
                  // open but is NOT persisted to prod.ingreso.
                  setObservacionesSaved(true);
                }}
                disabled={
                  observaciones === initialObservaciones || observacionesSaved
                }
                data-testid="tiquete-observaciones-guardar"
              >
                {t('tiquete_entrada_observaciones_guardar', {
                  defaultValue: 'Guardar',
                })}
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-2 text-sm">
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
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
          {/* REGRESSION fix (2026-09-22): only Imprimir + Ir a salida
              remain. Previously the footer had Siguiente + Anular +
              Hacer arqueo (the last three were stubs that only logged
              to console) — they cluttered the operator's success view
              without providing any real workflow hook. The Siguiente
              path is auto-fired by Imprimir (FEATURE F) so the operator
              no longer needs to click it manually. */}
          {onIrASalida && (
            <Button
              type="button"
              variant="outline"
              onClick={onIrASalida}
              data-testid="tiquete-ir-a-salida"
            >
              {t('tiquete_entrada_ir_a_salida', {
                defaultValue: 'Ir a salida',
              })}
            </Button>
          )}
          {/* FEATURE F: Imprimir — disabled when subscription is expired
              (FEATURE B gate). On success the dialog auto-closes via
              onSiguiente() so the operator doesn't need to click
              "Siguiente" separately. */}
          <Button
            type="button"
            onClick={handlePrint}
            disabled={!canPrint}
            aria-label={t('tiquete_entrada_imprimir', {
              defaultValue: 'Imprimir',
            })}
            data-testid="tiquete-imprimir"
          >
            {t('tiquete_entrada_imprimir', { defaultValue: 'Imprimir' })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
