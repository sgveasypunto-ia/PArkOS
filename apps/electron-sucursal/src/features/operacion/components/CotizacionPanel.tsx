/**
 * `<CotizacionPanel />` — pure presentational cotization panel (HU-F7.1 T3).
 *
 * Receives the canonical F1.8 discriminated-union `Cotizacion` (REQ-OPS-143)
 * and renders one of two branches:
 *   - `cobrar: true` (rotación) → semantic `<dl>` with formatCOP values.
 *   - `cobrar: false` (mensualidad) → info banner, no breakdown.
 *
 * Plus a 15-minute countdown that turns `text-destructive` + `<AlertTriangle
 * />` when `secondsLeft < 120` (REQ-OPS-146, OD-2 ratified). `aria-live` +
 * `role="alert"` for WCAG 2.1 AA (RNF-022).
 *
 * REQ-OPS-138 single-drawer invariant preserved: this component does NOT
 * own drawer state. The parent wires `onConfirmar` to
 * `useDashboardDrawerStore.open('pago', pagoAnchorId)` for rotación, or
 * to the HU-F7.2 mensualidad forwarder for `cobrar: false`.
 *
 * REQ-OPS-147: `formatCOP` is the ONLY monetary formatter. No raw
 * `.toLocaleString('es-CO') + '$'` concatenation.
 *
 * CU-02 detail (operador, 2026-09-22): la fila "Tarifa aplicada" del
 * desglose hace un lookup contra el backend para traer el detalle
 * completo (``valor``, ``valor_plena``, ``vigente_desde``,
 * ``vigente_hasta``, ``estado``). Antes de este cambio el panel
 * mostraba solo el UUID crudo. Hook ``useTarifaByUuid`` con SWR keyed
 * por uuid (5min deduping, 404 → fallback al UUID).
 *
 * R4 risk mitigation (R4 = countdown 60×/min re-render): wrapped in
 * `React.memo` so SalidaPanel doesn't re-render on every second tick.
 */
import * as React from 'react';

import { AlertTriangle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { formatCOP, formatFechaHoraCorta } from '../../caja/lib/format';
import type { Cotizacion } from '../hooks/useCotizacion';
import { useTarifaByUuid } from '../../catalogos/hooks/useTarifaByUuid';
import { ParkosHttpError } from '@parkos/ui-kit/fetch';

/**
 * `tarifasSucursalApi`'s `valor` / `valor_plena` are nullable columns
 * (a tarifa row can exist without a configured value). `formatCOP`
 * requires a `number`, so render `—` instead of calling it with `null`
 * (same fallback convention as `FacturaDisplayModal.money`).
 */
function formatCOPNullable(value: number | null): string {
  return value === null ? '—' : formatCOP(value);
}

export interface CotizacionPanelProps {
  /**
   * Canonical discriminated union (REQ-OPS-143). `cobrar === false`
   * short-circuits to the mensualidad info banner. `undefined` (with
   * `error` set) renders the `cotizar.errors.iva_no_configurado` banner
   * per REQ-OPS-148.
   */
  data: Cotizacion | undefined;
  /**
   * Optional fetch error from `useCotizacion`. When `status === 500` with
   * body `{"error":"iva_no_configurado"}`, the panel renders a
   * non-blocking info banner (REQ-OPS-148). All other errors also render
   * the banner — the operator dashboard must remain usable.
   */
  error?: Error | null;
  /** Seconds until `vigente_hasta` — from `useCountdown(15 * 60)`. */
  secondsLeft: number;
  /**
   * Parent wires to `useDashboardDrawerStore.open('pago', pagoAnchorId)`
   * for rotación, or to HU-F7.2 mensualidad forwarder for `cobrar ===
   * false`. REQ-OPS-138 single-drawer invariant preserved.
   */
  onConfirmar: () => void;
  /** Parent wires to SWR `mutate()` for manual re-fetch. */
  onRecalcular: () => void;
}

/**
 * Pure presentational component. Three render paths:
 *  - `error` set (iva_no_configurado or any 5xx) → REQ-OPS-148 banner.
 *  - `data.cobrar === false` → mensualidad info banner.
 *  - `data.cobrar === true` → semantic `<dl>` with formatCOP values.
 */
function CotizacionPanelImpl({
  data,
  error,
  secondsLeft,
  onConfirmar,
  onRecalcular,
}: CotizacionPanelProps): JSX.Element {
  const isExpiring = secondsLeft < 120;
  const isExpired = secondsLeft === 0;

  // CU-02 detail (operador, 2026-09-22): la fila "Tarifa aplicada"
  // hace un lookup contra el backend para traer el detalle completo
  // (``valor``, ``valor_plena``, ``vigente_desde``, ``vigente_hasta``,
  // ``estado``). Hook SWR keyed por uuid; 5min deduping; 404 → null
  // (el panel hace fallback al UUID). El SWR key es `null` cuando no
  // hay cotizacion de rotación (error branch o mensualidad branch) —
  // SWR skip en ese caso.
  const tarifaUuid: string | null =
    data && data.cobrar === true ? data.tarifa_uuid : null;
  const { tarifa } = useTarifaByUuid(tarifaUuid);

  // Error branch — non-blocking banner (REQ-OPS-148). The operator
  // dashboard must remain usable; this is NEVER a thrown error.
  if (error || !data) {
    const isIvaNoConfigurado =
      error instanceof ParkosHttpError && error.status === 500;
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cotización</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            role="alert"
            className="rounded border border-warning bg-warning/10 p-3 text-sm"
            data-testid="cotizacion-error-banner"
          >
            <p className="font-medium">
              {isIvaNoConfigurado
                ? 'IVA no configurado en el sistema. Contacte al administrador.'
                : 'No se pudo obtener la cotización'}
            </p>
            <p className="text-muted-foreground">
              {isIvaNoConfigurado
                ? 'La facturación requiere el impuesto IVA sembrado en el sistema.'
                : 'Reintente en unos segundos. Si persiste, contacte al administrador.'}
            </p>
          </div>

          <div className="mt-4">
            <Button
              type="button"
              variant="outline"
              data-testid="cotizacion-recalcular"
              onClick={onRecalcular}
            >
              Reintentar
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Mensualidad branch — short-circuits to the info banner (REQ-OPS-143
  // scenario 2). No `<dl>` rendered.
  if (data.cobrar === false) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Mensualidad vigente</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            role="status"
            className="rounded border border-info bg-info/10 p-3 text-sm"
            data-testid="cotizacion-mensualidad-banner"
          >
            <p className="font-medium">Vehículo con mensualidad</p>
            <p className="text-muted-foreground">
              Este vehículo tiene mensualidad vigente. La salida no genera cobro.
            </p>
          </div>

          <div
            aria-live="polite"
            data-testid="cotizacion-countdown"
            className="mt-2 text-xs text-muted-foreground"
          >
            Cotización válida
          </div>

          <div className="mt-4">
            <Button
              type="button"
              data-testid="cotizacion-confirmar"
              onClick={onConfirmar}
            >
              Confirmar salida por mensualidad
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Rotación branch — full fiscal breakdown (REQ-OPS-143 scenario 1).
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cotización</CardTitle>
      </CardHeader>
      <CardContent>
        <dl
          className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2"
          data-testid="cotizacion-dl"
        >
          <dt>Tiempo</dt>
          <dd>{data.tiempo_minutos}</dd>
          <dt>Subtotal</dt>
          <dd>{formatCOP(data.subtotal)}</dd>
          <dt>IVA</dt>
          <dd>{formatCOP(data.iva)}</dd>
          <dt className="font-semibold">Total a pagar</dt>
          <dd className="font-semibold" data-testid="cotizacion-total">
            {formatCOP(data.total)}
          </dd>
          <dt>Tarifa aplicada</dt>
          <dd data-testid="cotizacion-tarifa-detalle">
            {tarifa ? (
              <span>
                    {formatCOPNullable(tarifa.valor)}/min · Plena: {formatCOPNullable(tarifa.valor_plena)} ·{' '}
                    {tarifa.estado === 'activo' ? 'Vigente' : `Estado: ${tarifa.estado}`} desde{' '}
                    {formatFechaHoraCorta(tarifa.vigente_desde)}
                    {tarifa.vigente_hasta ? ` hasta ${formatFechaHoraCorta(tarifa.vigente_hasta)}` : ''}
                  </span>
            ) : (
              // Fallback: si el lookup falla (404, 5xx, o SWR sin
              // data todavía), mostramos el UUID como antes. El SWR
              // resuelve ~en el siguiente tick y el panel re-renderea
              // con el detalle completo.
              <span>{data.tarifa_uuid}</span>
            )}
          </dd>
          <dt>Cotización vigente hasta</dt>
          <dd>{formatFechaHoraCorta(data.vigente_hasta)}</dd>
        </dl>

        <div
          aria-live="polite"
          role={isExpiring ? 'alert' : undefined}
          className={
            isExpiring
              ? 'mt-2 flex items-center gap-1 text-xs text-destructive'
              : 'mt-2 text-xs text-muted-foreground'
          }
          data-testid="cotizacion-countdown"
        >
          {isExpiring && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
          <span>
            {isExpired
              ? 'Cotización expirada — recalculando…'
              : isExpiring
                ? 'Cotización expira pronto — confirma o recalcula'
                : `Tiempo restante: ${secondsLeft}s`}
          </span>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            type="button"
            data-testid="cotizacion-confirmar"
            onClick={onConfirmar}
          >
            Confirmar salida
          </Button>
          <Button
            type="button"
            variant="outline"
            data-testid="cotizacion-recalcular"
            onClick={onRecalcular}
          >
            Recalcular
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Memoized wrapper. R4 risk mitigation: countdown re-renders 60×/min;
 * without memoization, SalidaPanel re-renders too, polluting the F4.3
 * `useOcupacion` cadence and F6.1 SWR cache.
 */
export const CotizacionPanel = React.memo(CotizacionPanelImpl);
