/**
 * `<RenovarSuscripcionPanel />` — short renewal flow inside the
 * subscriptions drawer (PT-3): confirm + payment, NO plate entry (the
 * renewal re-launches the billing for the subscription's own plates).
 *
 * - "Renovar" is only reachable for subscriptions with `puede_renovar`
 *   (<= 10 days left, expired included); the UI never recalculates dates.
 * - Sends `POST /clientes/subscripciones/{uuid}/renovar` with an
 *   Idempotency-Key per ATTEMPT (`intentoId`): the same id is reused when
 *   a retry follows a network/5xx failure (replay, no double charge); a
 *   definitive 4xx answer starts a new attempt.
 * - On success shows the receipt (`<FacturaDisplayModal />` with the
 *   `factura` of the response) including the electronic-invoice state.
 * - PT-1: "Volver" returns to the previous screen (list / cupos) and is
 *   disabled while the payment is in flight and removed once charged.
 */
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { FacturaDisplayModal } from '../../facturacion/components/FacturaDisplayModal';
import { feWarningMessage } from '../../facturacion/lib/feEstado';
import {
  MEDIOS_PAGO_RENOVACION,
  RenovarSuscripcionRequestSchema,
  type MedioPagoRenovacion,
  type RenovarSuscripcionResponse,
} from '../api/renovacionApi';
import { RenovacionError, renovacionErrorMessage } from '../hooks/renovacionErrors';
import { useRenovarSuscripcion } from '../hooks/useRenovarSuscripcion';

export interface RenovarTarget {
  uuid: string;
  cliente_nombre: string;
  plan_nombre: string;
  fecha_vencimiento: string | null;
  dias_restantes: number | null;
  /** Plates of the subscription when the source list carries them. */
  placas?: string[];
}

export interface RenovarSuscripcionPanelProps {
  target: RenovarTarget;
  /** "Volver": previous screen (list or cupos). */
  onBack: () => void;
  /** Receipt dismissed after a successful renewal (parent refreshes + returns). */
  onRenovada: (result: RenovarSuscripcionResponse) => void;
  /** The backend answered the subscription is no longer renewable: refresh the lists. */
  onStale?: () => void;
  firePrintEnvelope?: (tipo: 'recibo_pago', payload: unknown) => void;
}

function defaultFirePrintEnvelope(tipo: 'recibo_pago', payload: unknown): void {
  const w = globalThis as unknown as {
    window?: { bridge?: { imprimir?: (k: string, p: unknown) => void } };
  };
  w.window?.bridge?.imprimir?.(tipo, payload);
}

const STALE_CODES: ReadonlySet<string> = new Set([
  'renovacion_fuera_de_ventana',
  'suscripcion_no_renovable',
  'subscripcion_no_encontrada',
]);

export function RenovarSuscripcionPanel({
  target,
  onBack,
  onRenovada,
  onStale,
  firePrintEnvelope,
}: RenovarSuscripcionPanelProps): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const { trigger, isMutating } = useRenovarSuscripcion();
  const [medioPago, setMedioPago] = useState<MedioPagoRenovacion>('efectivo');
  const [referencia, setReferencia] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [resultado, setResultado] = useState<RenovarSuscripcionResponse | null>(null);
  const [reciboAbierto, setReciboAbierto] = useState(false);
  const intentoRef = useRef<string>(crypto.randomUUID());

  const requiereVoucher = medioPago === 'datafono';
  const mostrarReferencia = medioPago !== 'efectivo';

  const errorMessage = useMemo(
    () => (error ? renovacionErrorMessage(error, t) : null),
    [error, t],
  );

  const handleConfirmar = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    if (isMutating || resultado) return;
    const parsed = RenovarSuscripcionRequestSchema.safeParse({
      medio_pago: medioPago,
      referencia: mostrarReferencia && referencia.trim() ? referencia.trim() : null,
    });
    if (!parsed.success) {
      setError(new RenovacionError(400, 'voucher_requerido'));
      return;
    }
    setError(null);
    try {
      const res = await trigger({
        ...parsed.data,
        uuid_subscripcion: target.uuid,
        intentoId: intentoRef.current,
      });
      setResultado(res);
      // No receipt to show (factura null): keep the confirmation card + "Cerrar".
      setReciboAbierto(res.factura !== null);
    } catch (err) {
      setError(err);
      if (err instanceof RenovacionError) {
        // A definitive answer closes this attempt: the next click is a new one.
        if (err.esDefinitivo) intentoRef.current = crypto.randomUUID();
        if (STALE_CODES.has(err.code)) onStale?.();
      }
    }
  };

  const handleReciboClose = (): void => {
    if (!resultado) return;
    const factura = resultado.factura;
    if (factura) {
      const emit = firePrintEnvelope ?? defaultFirePrintEnvelope;
      queueMicrotask(() => {
        try {
          emit('recibo_pago', {
            uuid_factura: factura.uuid,
            numero_recibo: factura.numero_recibo,
          });
        } catch (err) {
          console.warn('[Renovar] bridge.imprimir(recibo_pago) failed:', err);
        }
      });
    }
    setReciboAbierto(false);
    onRenovada(resultado);
  };

  const feWarning = resultado
    ? feWarningMessage(
        resultado.factura_electronica_error ?? resultado.factura?.factura_electronica_error,
        resultado.factura_electronica_pendiente ??
          resultado.factura?.factura_electronica_pendiente,
        t,
      )
    : null;

  return (
    <div className="m-auto w-full space-y-4" data-testid="renovar-panel">
      {!resultado && (
        <button
          type="button"
          onClick={onBack}
          disabled={isMutating}
          data-testid="renovar-volver"
          className="rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50"
        >
          ← {t('suscripciones:sheet.volver', { defaultValue: 'Volver' })}
        </button>
      )}

      <div className="rounded border bg-card px-3 py-2 text-sm" data-testid="renovar-resumen">
        <div className="font-medium">{target.cliente_nombre}</div>
        <div className="text-xs text-muted-foreground">{target.plan_nombre}</div>
        {target.fecha_vencimiento && (
          <div className="text-xs text-muted-foreground" data-testid="renovar-vencimiento">
            {t('suscripciones:sheet.vence', { defaultValue: 'Vence' })}:{' '}
            {target.fecha_vencimiento}
            {target.dias_restantes !== null &&
              ` (${
                target.dias_restantes < 0
                  ? t('suscripciones:renovar.vencida', { defaultValue: 'vencida' })
                  : t('suscripciones:renovar.diasRestantes', {
                      count: target.dias_restantes,
                      defaultValue_one: '{{count}} día restante',
                      defaultValue_other: '{{count}} días restantes',
                    })
              })`}
          </div>
        )}
        {target.placas && target.placas.length > 0 && (
          <div className="mt-1 font-mono text-xs uppercase" data-testid="renovar-placas">
            {target.placas.join(' · ')}
          </div>
        )}
      </div>

      <p className="text-sm text-muted-foreground" data-testid="renovar-nota">
        {t('suscripciones:renovar.nota', {
          defaultValue:
            'La renovación mantiene las placas de la suscripción y cobra el plan completo. No hace falta registrar placas.',
        })}
      </p>

      {!resultado && (
        <form
          className="space-y-3"
          onSubmit={(e) => void handleConfirmar(e)}
          data-testid="renovar-form"
        >
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="renovar-medio-pago">
              {t('suscripciones:renovar.medioPago', { defaultValue: 'Medio de pago' })}
            </label>
            <select
              id="renovar-medio-pago"
              data-testid="renovar-medio-pago"
              value={medioPago}
              onChange={(e) => {
                setMedioPago(e.target.value as MedioPagoRenovacion);
                setError(null);
              }}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              {MEDIOS_PAGO_RENOVACION.map((m) => (
                <option key={m} value={m}>
                  {t(`suscripciones:renovar.medios.${m}`, { defaultValue: MEDIO_LABEL[m] })}
                </option>
              ))}
            </select>
          </div>

          {mostrarReferencia && (
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="renovar-referencia">
                {requiereVoucher
                  ? t('suscripciones:renovar.voucher', { defaultValue: 'Voucher (datáfono)' })
                  : t('suscripciones:renovar.referencia', {
                      defaultValue: 'Referencia (opcional)',
                    })}
              </label>
              <Input
                id="renovar-referencia"
                data-testid="renovar-referencia"
                value={referencia}
                onChange={(e) => {
                  setReferencia(e.target.value);
                  setError(null);
                }}
                aria-required={requiereVoucher}
                maxLength={255}
              />
            </div>
          )}

          {errorMessage && (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="renovar-error"
            >
              {errorMessage}
            </p>
          )}

          <Button
            type="submit"
            disabled={isMutating}
            className="w-full"
            data-testid="renovar-confirmar"
          >
            {isMutating
              ? t('suscripciones:renovar.procesando', { defaultValue: 'Procesando…' })
              : t('suscripciones:renovar.confirmar', {
                  defaultValue: 'Confirmar renovación y cobrar',
                })}
          </Button>
        </form>
      )}

      {resultado && (
        <div
          role="status"
          className="space-y-2 rounded border bg-card px-3 py-2 text-sm"
          data-testid="renovar-exito"
        >
          <p className="font-medium">
            {t('suscripciones:renovar.exito', { defaultValue: 'Suscripción renovada.' })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('suscripciones:renovar.nuevoVencimiento', {
              fecha: resultado.fecha_vencimiento,
              defaultValue: 'Nuevo vencimiento: {{fecha}}',
            })}
          </p>
          {!reciboAbierto && (
            <Button
              type="button"
              onClick={() => onRenovada(resultado)}
              data-testid="renovar-cerrar"
            >
              {t('common:close', { defaultValue: 'Cerrar' })}
            </Button>
          )}
        </div>
      )}

      <FacturaDisplayModal
        factura={reciboAbierto ? (resultado?.factura ?? null) : null}
        onClose={handleReciboClose}
        warning={feWarning}
      />
    </div>
  );
}

const MEDIO_LABEL: Record<MedioPagoRenovacion, string> = {
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
  datafono: 'Datáfono',
  transferencia: 'Transferencia',
};
