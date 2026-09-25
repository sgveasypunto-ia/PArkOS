/**
 * `<PagoSheet />` — F8.1 right-side drawer for the payment flow
 * (REQ-OPS-138 single-drawer invariant + REQ-OPS-139 lazy-mount).
 *
 * The sheet is a THIN SHELL after F8.1's PagoModal extraction:
 *   - Mounts `<PagoModal />` inside `<Sheet>` (the form is owned by
 *     PagoModal; this file only handles drawer concerns).
 *   - Wires the `onSubmit` callback to `useRegistrarPago` +
 *     post-pago print triggers (DEC-SUC-27: CU-15S fires AFTER
 *     pago, then recibo de pago).
 *   - Manages focus restore on close (REQ-OPS-138 §Esc).
 *   - F8.1-b (2026-09-23): auto-annuls the `prod.salidas` row on
 *     ANY close-without-pay path (Cancelar button / X / overlay
 *     click / Escape) via `useAnularSalidaNoPagada` — otherwise the
 *     ingreso would stay `cerrado` (the matching `prod.salidas`
 *     row is already inserted by `<SalidaFlow>`'s `trigger()`
 *     call) and the operator could never recover the cobro.
 *     `prod.salidas` is `[A]` (append-only) so the only recovery
 *     path is a workflow `[L-W]` row in `prod.anulaciones` with
 *     `tipo_anulable='salida'`. The annulment is triggered
 *     unconditionally on close-without-pay per the operator's
 *     directive (2026-09-23): "hasta que no se cobre y se genere
 *     factura no se debe cerrar el registro de parqueo".
 *
 * Print envelope:
 *   - Both `bridge.imprimir('salida', payload)` (CU-15S) and
 *     `bridge.imprimir('recibo_pago', payload)` (recibo de pago)
 *     are deferred to the next microtask via `queueMicrotask` so
 *     the React render commit completes BEFORE the IPC round-trip
 *     begins.
 *   - Both calls are wrapped in `try/catch` — printer offline /
 *     disconnected MUST NOT block the operator (the pago is already
 *     persisted in `prod.factura`).
 */
import { useEffect, useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';
import { useRegistrarPago } from '../hooks/useRegistrarPago';
import { useAnularSalidaNoPagada } from '../hooks/useAnularSalidaNoPagada';
import { PagoModal, type PagoFormValues } from './PagoModal';
import { buildClienteFePayload } from '../lib/clienteFePayload';
import { useInvalidateConteosOperacion } from '../../operacion/hooks/useInvalidateConteosOperacion';
import { useAuth } from '@parkos/ui-kit/hooks';
import { useSesionActiva } from '../../caja/hooks/useSesionActiva';
import type { FacturaRead } from '../api/facturaApi';
import { FacturaDisplayModal } from './FacturaDisplayModal';

export interface PagoSheetProps {
  /**
   * UUID del ingreso activo que se está pagando. The store consumer
   * threads this through the `pagoContext` payload; the sheet reads
   * it from props because the form needs it for the POST body.
   */
  uuid_ingreso: string | null;
  /**
   * UUID of the just-created `prod.salidas` row from
   * `<SalidaFlow>`'s `useRegistrarSalida.trigger()` call. Required
   * for F8.1-b auto-annulment on close-without-pay; `null` falls
   * back to a plain close (legacy / hotkey-driven flow without a
   * prior salida, see DrawerHost.tsx comments).
   */
  uuid_salida: string | null;
  /** Pre-IVA base (`cotizacion.subtotal`) — sent as `FacturaCreate.subtotal`. */
  subtotal_cop: number;
  total_cop: number;
  /**
   * Bridge print-envelope emitter for CU-15S (F7.3) + recibo_pago
   * (F8.1). Defaults to `window.bridge?.imprimir(tipo, payload)`
   * via a tiny helper that swallows IPC failures (DEC-SUC-08). The
   * post-pago envelope sequence is DEC-SUC-27 verbatim: CU-15S
   * fires AFTER pago, then recibo de pago.
   */
  firePrintEnvelope?: (tipo: 'salida' | 'recibo_pago', payload: unknown) => void;
}

function defaultFirePrintEnvelope(
  tipo: 'salida' | 'recibo_pago',
  payload: unknown,
): void {
  const w = globalThis as unknown as { window?: { bridge?: { imprimir?: (k: string, p: unknown) => void } } };
  const bridge = w.window?.bridge;
  if (bridge?.imprimir) {
    bridge.imprimir(tipo, payload);
  }
}

function deferredSafePrint(
  emit: (tipo: 'salida' | 'recibo_pago', payload: unknown) => void,
  tipo: 'salida' | 'recibo_pago',
  payload: unknown,
): void {
  queueMicrotask(() => {
    try {
      emit(tipo, payload);
    } catch (err) {
      console.warn(
        `[PagoSheet] bridge.imprimir(${tipo}) failed (printer_offline / disconnected):`,
        err,
      );
    }
  });
}

/**
 * `<PagoSheet />` — thin shell that mounts `<PagoModal>` inside the
 * right-side drawer, wires `useRegistrarPago` to the submit handler,
 * fires the post-pago print envelopes (DEC-SUC-27), and auto-annuls
 * the `prod.salidas` row on any close-without-pay path (F8.1-b,
 * 2026-09-23).
 */
export function PagoSheet({
  uuid_ingreso,
  uuid_salida,
  subtotal_cop,
  total_cop,
  firePrintEnvelope,
}: PagoSheetProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);
  const navigate = useNavigate();
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const { trigger } = useRegistrarPago();
  // F8.1-b (2026-09-23): auto-annul the salida on close-without-pay.
  // The `trigger` is awaited asynchronously after the sheet unmounts
  // — the operator is already moving on. Failures are logged but do
  // NOT block the next cobro.
  const { trigger: anularSalidaNoPagada } = useAnularSalidaNoPagada();
  // REGRESSION fix (2026-09-22, directiva del operador): after a
  // successful pago, the ingreso is fully closed — the live-count
  // SWR caches (cupos libres / vehiculos dentro / mi turno) must
  // re-fetch immediately so the operator sees the post-pago state
  // in the same frame. Without this, the right-sidebar panels keep
  // showing the pre-pago count for up to 15s, which makes them look
  // "hardcoded".
  const invalidarConteos = useInvalidateConteosOperacion();
  const { sucursal } = useAuth();
  const { sesion } = useSesionActiva();

  const open = openDrawer === 'pago';

  // HU-F8.4: hold the FacturaRead from the post-pago POST so we can
  // mount `<FacturaDisplayModal />` over the PagoSheet with the full
  // breakdown (minutos, segregación de valores, impuestos, datos
  // sucursal/cliente/vehículo). Set inside `handleSubmit` AFTER the
  // trigger resolves. Cleared when the operator dismisses the modal.
  const [facturaDisplay, setFacturaDisplay] = useState<FacturaRead | null>(null);

  // F8.1-b (2026-09-23): `pagadoRef` is the source of truth for "did
  // the operator actually confirm the pago?". We use a ref (not
  // state) so the value is captured by the `onOpenChange` closure
  // without re-mounting the Sheet on every flag flip. Set to `true`
  // inside `handleSubmit` AFTER the `trigger()` promise resolves
  // successfully (the await before the flip is intentional — we
  // don't want to mark paid if the POST failed and the form will
  // keep the modal open with the inline error).
  const pagadoRef = useRef(false);

  // Focus restore per REQ-OPS-138 §Esc.
  useEffect(() => {
    if (!open && lastAnchorId) {
      const anchor = document.getElementById(lastAnchorId);
      anchor?.focus();
    }
  }, [open, lastAnchorId]);

  // F8.1-b (2026-09-23): when the drawer closes, decide whether to
  // auto-annul the salida. This single handler covers EVERY close
  // path:
  //   - "Cancelar" button → `close()` → `openDrawer=null` →
  //     `onOpenChange(false)` → this handler fires
  //   - Sheet "X" button → same path
  //   - Overlay click → same path
  //   - Escape key → same path
  //   - Successful pago → `handleSubmit` sets `pagadoRef.current =
  //     true` BEFORE calling `close()`, so by the time this handler
  //     runs the flag is set and we skip the annulment
  //
  // The annulment is fire-and-forget — `void` the promise so the
  // close path stays synchronous. Failures are logged with
  // `console.warn` (the operator already dismissed the modal; we
  // don't block the next cobro, but we DO leave a trail for the
  // session-end audit hook).
  const handleClose = useCallback((): void => {
    if (pagadoRef.current) {
      // Happy path: pago confirmado, no annulment needed.
      close();
      return;
    }
    if (uuid_salida) {
      // Close-without-pay: annul the salida so the ingreso returns
      // to `abierto` in `V_INGRESO_ESTADO` and the operator can
      // collect on the next visit (or any other shift).
      void anularSalidaNoPagada({ uuid_salida })
        .catch((err: unknown) => {
          console.warn(
            '[PagoSheet] auto-annul failed (the ingreso will stay cerrado; manual recovery required):',
            err,
          );
        })
        .finally(() => {
          close();
        });
      return;
    }
    // Legacy / hotkey-driven flow without a prior salida — nothing
    // to annul, just close.
    close();
  }, [close, uuid_salida, anularSalidaNoPagada]);

  const handleSubmit = useCallback(
    async (values: PagoFormValues): Promise<void> => {
      // HU-F8.4 (BE↔FE fix, 2026-09-23): the BE's FacturaCreate
      // requires ``uuid_salida`` (the salida created by
      // ``POST /operacion/salidas`` before the pago). The previous
      // FE sent ``uuid_ingreso`` and the BE rejected with 422
      // (silent pago). ``uuid_salida`` is now in pagoContext per
      // ``fix/hu-f8-1-anular-salida-no-pagada`` (commit ``c7c19d2``).
      if (!uuid_salida) {
        // Defensive: PagoSheet shouldn't be reachable without a
        // salida, but if it is, surface a clear error instead of
        // sending a malformed POST.
        console.error('[PagoSheet] uuid_salida missing — cannot POST /facturacion/factura');
        return;
      }
      // Build the discriminated POST payload from the form values.
      // Bug 22 (2026-09-23): the BE's `FacturaCreate` requires a
      // non-empty `items[]` (does NOT derive them server-side) and
      // has NO `cliente` field — consumidor final is the default
      // (`fe_con_datos` omitted), a named invoice sets
      // `fe_con_datos: true` + `fe_datos_cliente`. `total` is
      // validated against `sum(item.valor_unitario * item.cantidad)`
      // (see `repo.factura.compute_total`), so the single line item
      // carries `valor_unitario: total_cop` (the PL/pgSQL cotización
      // base), NOT `subtotal_cop`. `subtotal_cop` only feeds the
      // display-only `subtotal` field. `datafono` voucher travels as
      // `referencia`, not `voucher` (see facturaApi.ts contract note).
      const items = [
        {
          tipo: 'servicio' as const,
          concepto: 'Servicio de parqueo',
          cantidad: 1,
          valor_unitario: total_cop,
        },
      ];
      const feDatos = buildClienteFePayload(values);
      const post = values.medio_pago === 'efectivo'
        ? {
            uuid_salida,
            medio_pago: 'efectivo' as const,
            items,
            subtotal: subtotal_cop,
            total: total_cop,
            ...feDatos,
          }
        : {
            uuid_salida,
            medio_pago: 'datafono' as const,
            items,
            subtotal: subtotal_cop,
            total: total_cop,
            referencia: values.voucher,
            ...feDatos,
          };
      const result = await trigger(post);
      // F8.1-b: mark `pagadoRef = true` BEFORE close so the
      // auto-annul branch in `handleClose` is skipped. We set this
      // AFTER the `await` resolves — if the POST failed the form
      // stays open with an inline error and the ref stays `false`,
      // which is the correct behaviour (a failed POST is a
      // close-without-pay scenario from the ingreso's POV).
      pagadoRef.current = true;
      // REGRESSION fix (2026-09-22): invalidate the live-count SWR
      // caches so the dashboard panels (Mi Turno / Inventario /
      // Vehículos dentro) re-fetch immediately after the pago. The
      // ingreso is fully closed at this point (factura + salida
      // persisted), so the cupos-libres + vehiculos-dentro panels
      // MUST reflect the new state in the same frame as the recibo.
      void invalidarConteos({
        uuid_sucursal: sucursal?.uuid ?? null,
        uuid_sesion: sesion?.uuid ?? null,
      });
      // HU-F8.4 — open the post-pago display modal with the full
      // breakdown (minutos + segregación de valores + impuestos +
      // datos sucursal/cliente/vehículo). The modal is the
      // operator-facing confirmation; the thermal print fires in
      // parallel per DEC-SUC-27.
      setFacturaDisplay(result);
      // HU-F8.2 (REQ-OPS-169/170) — navigate to the FE detail page if
      // the pago created an electronic invoice. The discriminated
      // FacturaReadSchema enforces ``factura_electronica.estado_dian``
      // so a missing/null FE just falls through to the normal close
      // + print sequence.
      if (result.factura_electronica && result.factura_electronica.uuid) {
        navigate(`/factura-electronica/${result.factura_electronica.uuid}`);
      }
      // DEC-SUC-27 — CU-15S print fires AFTER pago, then recibo de pago.
      const emit = firePrintEnvelope ?? defaultFirePrintEnvelope;
      deferredSafePrint(emit, 'salida', { uuid_factura: result.uuid });
      deferredSafePrint(emit, 'recibo_pago', {
        uuid_factura: result.uuid,
        numero_recibo: result.numero_recibo,
      });
      // NOTE: close() happens when the operator dismisses the
      // FacturaDisplayModal, not here. The drawer stays open with
      // the modal mounted until the operator closes it.
    },
    [uuid_salida, subtotal_cop, total_cop, trigger, firePrintEnvelope, navigate, invalidarConteos, sucursal?.uuid, sesion?.uuid],
  );

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) handleClose();
      }}
    >
      {/* F31.3 — el Sheet base es `w-full md:w-1/2`; en pantallas anchas
          (2560/3840/ultrawide) la mitad del viewport estira un
          formulario de una sola columna a un ancho absurdo. `sm:max-w-md`
          topea el crecimiento SIN tocar `ui/sheet.tsx` (compartido con
          otros dominios) — por debajo de `md` sigue siendo full-width. */}
      <SheetContent side="right" data-testid="pago-sheet" className="overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{t('facturacion:pago.titulo', { defaultValue: 'Cobrar' })}</SheetTitle>
          <SheetDescription>
            {t('facturacion:pago.descripcion', {
              defaultValue: 'Registra el pago y emite la factura.',
            })}
          </SheetDescription>
        </SheetHeader>

        <PagoModal
          uuid_ingreso={uuid_ingreso}
          total_cop={total_cop}
          onSubmit={handleSubmit}
        />

        <SheetFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleClose()}
            data-testid="pago-cancelar"
          >
            {t('common:cancel', { defaultValue: 'Cancelar' })}
          </Button>
        </SheetFooter>

        {/* HU-F8.4 — post-pago display modal mounted over the sheet.
            Renders the full FacturaRead breakdown (minutos, items,
            impuestos, sucursal, vehiculo, cliente). The modal's
            close handler clears the state AND closes the sheet so
            the operator returns to the dashboard with the cupos
            already invalidated. */}
        <FacturaDisplayModal
          factura={facturaDisplay}
          onClose={() => {
            setFacturaDisplay(null);
            close();
          }}
        />
      </SheetContent>
    </Sheet>
  );
}