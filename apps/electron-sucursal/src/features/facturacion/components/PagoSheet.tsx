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
import { useEffect, useCallback } from 'react';
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
import { PagoModal, type PagoFormValues } from './PagoModal';

export interface PagoSheetProps {
  /**
   * UUID del ingreso activo que se está pagando. The store consumer
   * threads this through the `pagoContext` payload; the sheet reads
   * it from props because the form needs it for the POST body.
   */
  uuid_ingreso: string | null;
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
 * and fires the post-pago print envelopes (DEC-SUC-27).
 */
export function PagoSheet({
  uuid_ingreso,
  total_cop,
  firePrintEnvelope,
}: PagoSheetProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);
  const navigate = useNavigate();
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const { trigger } = useRegistrarPago();

  const open = openDrawer === 'pago';

  // Focus restore per REQ-OPS-138 §Esc.
  useEffect(() => {
    if (!open && lastAnchorId) {
      const anchor = document.getElementById(lastAnchorId);
      anchor?.focus();
    }
  }, [open, lastAnchorId]);

  const handleSubmit = useCallback(
    async (values: PagoFormValues): Promise<void> => {
      if (!uuid_ingreso) return;
      // Build the discriminated POST payload from the form values.
      const post = values.medio_pago === 'efectivo'
        ? {
            uuid_ingreso,
            medio_pago: 'efectivo' as const,
            monto_recibido_cents: values.monto_recibido_cop,
            total_cents: total_cop,
            cliente: {
              nit: values.fe ? values.nit ?? '' : '222222222222222',
              nombre: values.fe ? values.nombre_cliente ?? 'Consumidor final' : 'Consumidor final',
              email: values.fe ? values.email_cliente ?? null : null,
            },
          }
        : {
            uuid_ingreso,
            medio_pago: 'datafono' as const,
            total_cents: total_cop,
            voucher: values.voucher,
            cliente: {
              nit: values.fe ? values.nit ?? '' : '222222222222222',
              nombre: values.fe ? values.nombre_cliente ?? 'Consumidor final' : 'Consumidor final',
              email: values.fe ? values.email_cliente ?? null : null,
            },
          };
      const result = await trigger(post);
      // HU-F8.2 (REQ-OPS-169/170) — navigate to the FE detail page if
      // the pago created an electronic invoice. The `as` cast is
      // defensive — `FacturaReadSchema.factura_electronica: z.unknown()`
      // (ABIERTO-F8.2-01 follow-up tightens this). Narrow via
      // `typeof` so a missing/null/unknown FE just falls through to
      // the normal close + print sequence.
      const fe = result.factura_electronica as { uuid?: unknown } | null | undefined;
      if (fe && typeof fe === 'object' && typeof fe.uuid === 'string') {
        navigate(`/factura-electronica/${fe.uuid}`);
      }
      // DEC-SUC-27 — CU-15S print fires AFTER pago, then recibo de pago.
      const emit = firePrintEnvelope ?? defaultFirePrintEnvelope;
      deferredSafePrint(emit, 'salida', { uuid_factura: result.uuid });
      deferredSafePrint(emit, 'recibo_pago', {
        uuid_factura: result.uuid,
        numero_recibo: result.numero_recibo,
      });
      close();
    },
    [uuid_ingreso, total_cop, trigger, firePrintEnvelope, close, navigate],
  );

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent side="right" data-testid="pago-sheet">
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
            onClick={() => close()}
            data-testid="pago-cancelar"
          >
            {t('common:cancel', { defaultValue: 'Cancelar' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}