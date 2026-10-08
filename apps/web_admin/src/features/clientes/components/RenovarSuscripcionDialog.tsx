/**
 * `<RenovarSuscripcionDialog />` — confirmación de renovación (PT-3).
 *
 * Renews an EXISTING subscription (no plates are asked: the backend reuses the
 * vehicles of the previous period). The "Renovar" entry point is only shown by
 * the caller when the server says `puede_renovar` (any open subscription:
 * there is no anticipation window, expired included); this dialog never
 * recomputes that. For an early renewal it only previews the day the new
 * period starts (due date + 1); the backend confirms the real dates.
 *
 * Idempotency: one `Idempotency-Key` per attempt. A retry of the SAME request
 * (e.g. after a network error) reuses the key so the backend replays instead
 * of charging twice; changing the payment data rotates the key, otherwise the
 * backend would answer `idempotency_key_conflict`.
 */
import { useEffect, useRef, useState } from 'react';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import {
  ClientesApiError,
  MEDIOS_PAGO_RENOVACION,
  newIdempotencyKey,
  renovarSubscripcion,
  type MedioPagoRenovacion,
  type RenovacionResponse,
  type SubscripcionCliente,
} from '../api/clientesApi';
import { mapRenovacionError } from '../lib/errorMessages';

export interface RenovarSuscripcionDialogProps {
  subscripcion: SubscripcionCliente | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful renewal so the parent can refresh its list. */
  onRenewed: (result: RenovacionResponse) => void | Promise<void>;
}

const MEDIO_LABELS: Record<MedioPagoRenovacion, [string, string]> = {
  efectivo: ['renovacion.medio.efectivo', 'Efectivo'],
  tarjeta: ['renovacion.medio.tarjeta', 'Tarjeta'],
  datafono: ['renovacion.medio.datafono', 'Datáfono'],
  transferencia: ['renovacion.medio.transferencia', 'Transferencia'],
};

/** Day after `iso` (YYYY-MM-DD), calendar-safe (month/year/leap) via UTC. */
function diaSiguiente(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + 1)).toISOString().slice(0, 10);
}

function formatCop(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return n.toLocaleString('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
}

export function RenovarSuscripcionDialog({
  subscripcion,
  open,
  onOpenChange,
  onRenewed,
}: RenovarSuscripcionDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [medioPago, setMedioPago] = useState<MedioPagoRenovacion>('efectivo');
  const [referencia, setReferencia] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RenovacionResponse | null>(null);
  // The previous attempt ended without a definitive answer (network error /
  // 5xx): the server may have processed it. Keep the SAME key and the SAME
  // payment data so a retry is replayed by the backend instead of charging
  // twice; the payment fields are locked until a definitive answer arrives.
  const [ambiguous, setAmbiguous] = useState(false);
  const keyRef = useRef<string | null>(null);
  const currentKey = (): string => {
    if (keyRef.current === null) keyRef.current = newIdempotencyKey();
    return keyRef.current;
  };
  const rotateKey = (): void => {
    keyRef.current = newIdempotencyKey();
  };
  // Never close while a request is in flight (the outcome would be lost).
  const handleOpenChange = (next: boolean): void => {
    if (!next && submitting) return;
    onOpenChange(next);
  };

  useEffect(() => {
    if (open) {
      setAmbiguous(false);
      setMedioPago('efectivo');
      setReferencia('');
      setError(null);
      setResult(null);
      setSubmitting(false);
      rotateKey();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, subscripcion?.uuid]);

  const anticipada = (subscripcion?.dias_restantes ?? 0) > 0;
  const referenciaRequerida = medioPago === 'datafono';
  const referenciaFaltante = referenciaRequerida && referencia.trim() === '';

  async function confirmar(): Promise<void> {
    if (!subscripcion || submitting) return;
    if (referenciaFaltante) {
      setError(t('renovacion.errorVoucher', 'El datáfono exige la referencia del voucher.'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await renovarSubscripcion(
        subscripcion.uuid,
        { medio_pago: medioPago, referencia: referencia.trim() || null },
        currentKey(),
      );
      setResult(res);
      setAmbiguous(false);
      await onRenewed(res);
    } catch (e) {
      // A definitive 4xx means the server did NOT renew: payment data may be
      // corrected with a fresh key. Anything else (network, timeout, 5xx) is
      // ambiguous: keep key + data for a replay-safe retry.
      const definitivo = e instanceof ClientesApiError && e.status >= 400 && e.status < 500;
      if (definitivo) rotateKey();
      setAmbiguous(!definitivo);
      setError(mapRenovacionError(e, t));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent data-testid="renovar-dialog">
        <DialogHeader>
          <DialogTitle>{t('renovacion.titulo', 'Renovar suscripción')}</DialogTitle>
          <DialogDescription>
            {t(
              'renovacion.descripcion',
              'Se renueva la suscripción con sus mismos vehículos y se cobra el plan completo (IVA incluido). No es necesario ingresar placas.',
            )}
          </DialogDescription>
        </DialogHeader>

        {result === null && anticipada && subscripcion?.fecha_vencimiento && (
          <p
            className="rounded-md border px-3 py-2 text-sm"
            data-testid="renovar-vigencia-anticipada"
          >
            {t(
              'renovacion.vigenciaAnticipada',
              'La nueva vigencia empieza el {{inicio}} y se suma a los {{dias}} días restantes.',
              {
                inicio: diaSiguiente(subscripcion.fecha_vencimiento),
                dias: subscripcion.dias_restantes,
              },
            )}
          </p>
        )}

        {result === null ? (
          <form
            className="grid gap-4"
            data-testid="renovar-form"
            onSubmit={(e) => {
              e.preventDefault();
              void confirmar();
            }}
            noValidate
          >
            {error !== null && (
              <p
                role="alert"
                aria-live="assertive"
                data-testid="renovar-error"
                className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {error}
              </p>
            )}
            {ambiguous && (
              <p role="status" data-testid="renovar-ambiguo" className="text-sm text-muted-foreground">
                {t(
                  'renovacion.ambiguo',
                  'No se recibió respuesta del servidor y la renovación pudo haberse procesado. Reintente con los mismos datos (no se cobrará dos veces) o cierre y revise la lista.',
                )}
              </p>
            )}

            <div className="grid gap-2">
              <Label htmlFor="renovar-medio-pago">{t('renovacion.medioPago', 'Medio de pago')}</Label>
              <select
                id="renovar-medio-pago"
                data-testid="renovar-medio-pago"
                value={medioPago}
                disabled={submitting || ambiguous}
                onChange={(e) => {
                  setMedioPago(e.target.value as MedioPagoRenovacion);
                  rotateKey();
                  setError(null);
                }}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {MEDIOS_PAGO_RENOVACION.map((m) => (
                  <option key={m} value={m}>
                    {t(MEDIO_LABELS[m][0], MEDIO_LABELS[m][1])}
                  </option>
                ))}
              </select>
            </div>

            {medioPago !== 'efectivo' && (
              <div className="grid gap-2">
                <Label htmlFor="renovar-referencia">
                  {t('renovacion.referencia', 'Referencia')}
                  {referenciaRequerida && (
                    <span className="text-destructive" aria-hidden="true">
                      {' '}*
                    </span>
                  )}
                </Label>
                <Input
                  id="renovar-referencia"
                  data-testid="renovar-referencia"
                  value={referencia}
                  disabled={submitting || ambiguous}
                  required={referenciaRequerida}
                  aria-required={referenciaRequerida}
                  aria-invalid={referenciaFaltante && error !== null ? 'true' : 'false'}
                  onChange={(e) => {
                    setReferencia(e.target.value);
                    rotateKey();
                    setError(null);
                  }}
                />
              </div>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
                disabled={submitting}
              >
                {t('common.cancel', 'Cancelar')}
              </Button>
              <Button type="submit" disabled={submitting} data-testid="renovar-confirmar">
                {submitting
                  ? t('common.saving', 'Guardando…')
                  : t('renovacion.confirmar', 'Confirmar renovación')}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="grid gap-3" data-testid="renovar-resultado" role="status">
            <p className="text-sm">
              {t(
                'renovacion.exito',
                'Suscripción renovada. Nuevo periodo: {{inicio}} → {{vencimiento}}.',
                {
                  inicio: result.fecha_inicio_cobertura ?? '—',
                  vencimiento: result.fecha_vencimiento ?? '—',
                },
              )}
            </p>
            <p className="text-sm text-muted-foreground">
              {t('renovacion.total', 'Total cobrado (IVA incluido): {{total}}', {
                total: formatCop(result.total_con_iva),
              })}
            </p>
            {result.factura_electronica_error ? (
              <p
                role="alert"
                data-testid="renovar-fe-error"
                className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-3 py-2 text-sm"
              >
                {result.factura_electronica_pendiente
                  ? t(
                      'renovacion.fePendiente',
                      'La renovación se registró, pero la factura electrónica no se pudo emitir todavía; se reintentará automáticamente y quedó una alerta para el administrador.',
                    )
                  : t(
                      'renovacion.feError',
                      'La renovación se registró, pero la factura electrónica no se pudo emitir todavía. Quedó una alerta para el administrador.',
                    )}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" onClick={() => onOpenChange(false)} data-testid="renovar-cerrar">
                {t('common.close', 'Cerrar')}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
