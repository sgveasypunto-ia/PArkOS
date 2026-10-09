/**
 * `<MiTurnoPanel />` — operator-facing per-turn widget (HU-F12.1).
 *
 * Además de las métricas operativas (ingresos, salidas, cupos libres),
 * muestra el dinero cobrado en efectivo durante el turno
 * (`total_cobrado_efectivo_cop`), de sólo lectura. El datáfono NO se
 * muestra: el BE lo fija en 0 a propósito (F12.1.1 / REQ-OPS-197) y un
 * cero ahí sería un dato falso. El valor sólo se pinta cuando el hook
 * trae datos reales (`isLoaded`); si no, `—` (nunca un 0 inventado).
 *
 * Diseño tipo LISTA vertical (no KPI cards en grid) consistente con
 * `<OcupacionPanel />` que está justo debajo en el sidebar derecho.
 *
 * Filas renderizadas:
 *   1. Ingresos en mi turno    (count, MiTurnoRead.ingresos_count)
 *   2. Salidas en mi turno     (count, MiTurnoRead.salidas_count)
 *   3. Cupos libres en sucursal (sum de OcupacionItem.disponible,
 *      computado client-side; sólo tipos con cupo_maximo > 0)
 *
 * El ArqueoButton se sacó del panel (2026-09-22 — directiva del
 * operador) — ahora vive solo en el sidebar izquierdo (`data-testid=
 * "sidebar-arqueo"`) + atajo F4. El panel Mi Turno queda como vista
 * informativa de sólo-lectura: rows de números, sin CTAs. "Cerrar
 * turno" sigue en el header del dashboard (single source of truth).
 *
 * Zero-state contract (REQ-OPS-187, DA-F12.1-4): cuando `uuid_sesion`
 * es `null` o el SWR no pobló, el panel renderiza ceros sin skeleton /
 * error UI. `useMiTurno` lo garantiza vía `emptyMiTurno`. Cupos libres
 * en load-state (`useOcupacion` aún sin datos) renderiza `—` para
 * distinguir "no sé" de "0".
 */
import { useTranslation } from 'react-i18next';

import { formatCOP } from '../../caja/lib/format';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import { useMiTurno } from '../hooks/useMiTurno';
import { useOcupacion } from '../hooks/useOcupacion';

export interface MiTurnoPanelProps {
  /**
   * Active operator turno UUID. `null` → zero-state (el hook retorna
   * `MiTurnoRead` con todos los counts en 0; el panel renderiza 0s
   * sin skeleton / error UI — DA-F12.1-4).
   */
  uuid_sesion: string | null;
  /**
   * Branch UUID — drives `useOcupacion` para cupos libres per-branch.
   * `null` → cupos libres renderiza `—` (load-state, no se inventa 0).
   */
  uuid_sucursal: string | null;
}

export function MiTurnoPanel({
  uuid_sesion,
  uuid_sucursal,
}: MiTurnoPanelProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const { data, error, isStale, isLoaded } = useMiTurno(uuid_sesion);
  const { data: ocupacionData } = useOcupacion(uuid_sucursal);

  // Defensive `?? 0` keeps the type narrow in case the SWR shape drifts.
  const ingresos = data?.ingresos_count ?? 0;
  const salidas = data?.salidas_count ?? 0;
  const efectivoCobrado =
    isLoaded && data ? formatCOP(data.total_cobrado_efectivo_cop) : '—';
  const cobradoConError = !isLoaded && error !== undefined;

  // Cupos libres = sum de `disponible` a través de los tipos
  // admin-configured (cupo_maximo > 0). Unconfigured tipos
  // (cupo_maximo = 0) se excluyen — no son "cupos" reales a contar.
  // `disponible` viene computado server-side (DEC-SUC-11); el cliente
  // NUNCA lo re-deriva.
  const cuposLibres =
    ocupacionData?.items
      .filter((it) => it.cupo_maximo > 0)
      .reduce((acc, it) => acc + it.disponible, 0) ?? null;

  return (
    <Card
      data-testid="mi-turno-panel"
      data-stale={isStale ? 'true' : 'false'}
      className="overflow-hidden border-border/60"
    >
      <CardHeader className="px-5 pt-4 pb-3">
        <CardTitle className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
          {t('miTurno.titulo')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 px-3 pb-4">
        {/*
          Lista vertical con divisor entre filas; las label a la izquierda
          (text-muted-foreground, peso regular) y el número a la derecha
          con `font-mono tabular-nums` para que no jitter cuando cambian
          los dígitos. Cada fila tiene `data-testid="mi-turno-row-..."`
          para el suite vitest. Sin CTA al pie — el Arqueo vive en el
          sidebar izquierdo (directiva 2026-09-22).
        */}
        <ul
          role="list"
          data-testid="mi-turno-list"
          className="divide-y divide-border/40 text-sm"
        >
          <li
            data-testid="mi-turno-row-ingresos"
            className="flex items-center justify-between py-2.5"
          >
            <span className="text-muted-foreground/90 text-sm">
              {t('miTurno.kpis.ingresos')}
            </span>
            <span className="font-mono text-2xl font-semibold tabular-nums tracking-tight">{ingresos}</span>
          </li>
          <li
            data-testid="mi-turno-row-salidas"
            className="flex items-center justify-between py-2.5"
          >
            <span className="text-muted-foreground/90 text-sm">
              {t('miTurno.kpis.salidas')}
            </span>
            <span className="font-mono text-2xl font-semibold tabular-nums tracking-tight">{salidas}</span>
          </li>
          <li
            data-testid="mi-turno-row-cupos-libres"
            className="flex items-center justify-between py-2.5"
          >
            <span className="text-muted-foreground/90 text-sm">
              {t('miTurno.kpis.cuposLibres')}
            </span>
            <span
              className="font-mono text-2xl font-semibold tabular-nums tracking-tight"
              data-testid="mi-turno-cupos-libres-value"
            >
              {cuposLibres ?? '—'}
            </span>
          </li>
        </ul>
        <section
          role="region"
          aria-label={t('miTurno.cobrado.regionLabel')}
          data-testid="mi-turno-cobrado"
          className="mt-1 border-t border-border/40 px-0 pt-2.5"
        >
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground/90 text-sm">
              {t('miTurno.cobrado.efectivo')}
            </span>
            <span
              className="font-mono text-xl font-semibold tabular-nums tracking-tight"
              data-testid="mi-turno-cobrado-efectivo-value"
            >
              {efectivoCobrado}
            </span>
          </div>
          {cobradoConError && (
            <p role="alert" className="mt-1 text-xs text-destructive">
              {t('miTurno.cobrado.error')}
            </p>
          )}
        </section>
      </CardContent>
    </Card>
  );
}