/**
 * `<MiTurnoPanel />` — operator-facing per-turn widget (HU-F12.1).
 *
 * Directiva del operador (2026-09-22 — feedback de testing en kiosk):
 * la sección debe mostrar exclusivamente métricas operativas del turno
 * más cupos libres de la sucursal. NO incluye dinero (totalCobrado /
 * efectivo / datafono) — esos campos siguen llegando en el wire
 * `MiTurnoRead` por el contrato BE locked (DA-F12.1-1 GATING:
 * `backend/tests/unit/test_mi_turno_schema.py` y `apps/electron-
 * sucursal/src/lib/api/schemas/__tests__/mi-turno.test.ts` leen el
 * key-set del wire; tocar la Zod schema requiere tocar ambos). El
 * panel simplemente deja de renderizarlos.
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
  const { data, isStale } = useMiTurno(uuid_sesion);
  const { data: ocupacionData } = useOcupacion(uuid_sucursal);

  // Defensive `?? 0` keeps the type narrow in case the SWR shape drifts.
  const ingresos = data?.ingresos_count ?? 0;
  const salidas = data?.salidas_count ?? 0;

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
      className="overflow-hidden"
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-sm uppercase tracking-wider text-muted-foreground">
          {t('miTurno.titulo')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-2">
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
          className="divide-y divide-border text-sm"
        >
          <li
            data-testid="mi-turno-row-ingresos"
            className="flex items-center justify-between py-1.5"
          >
            <span className="text-muted-foreground">
              {t('miTurno.kpis.ingresos')}
            </span>
            <span className="font-mono text-lg tabular-nums">{ingresos}</span>
          </li>
          <li
            data-testid="mi-turno-row-salidas"
            className="flex items-center justify-between py-1.5"
          >
            <span className="text-muted-foreground">
              {t('miTurno.kpis.salidas')}
            </span>
            <span className="font-mono text-lg tabular-nums">{salidas}</span>
          </li>
          <li
            data-testid="mi-turno-row-cupos-libres"
            className="flex items-center justify-between py-1.5"
          >
            <span className="text-muted-foreground">
              {t('miTurno.kpis.cuposLibres')}
            </span>
            <span
              className="font-mono text-lg tabular-nums"
              data-testid="mi-turno-cupos-libres-value"
            >
              {cuposLibres ?? '—'}
            </span>
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}