/**
 * `<MiTurnoPanel />` — operator-facing per-turn KPI aggregate widget
 * (HU-F12.1, REQ-OPS-187).
 *
 * Mounted in `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`
 * right sidebar ABOVE `<OcupacionPanel />`. The panel renders a shadcn
 * `<Card>` strip with 5 KPI cells (ingresos / salidas / totalCobrado /
 * efectivo / datafono) and a footer action row with two per-turn
 * buttons (F11.3):
 *   - `<ArqueoButton />` opens the right-side ArqueoParcial drawer
 *     (HU-F10.1 auditoría del turno — sin cierre). Mounted by
 *     <DrawerHost /> in the dashboard so no route navigation.
 *   - `<CerrarTurnoButton />` navigates to `/caja/cerrar-turno` for the
 *     F10.2 close flow (no business logic here — close flow is F10.2's
 *     responsibility).
 *
 * The two buttons sit side-by-side because they are the two per-turn
 * caja actions the operator owns while a sesion is active. The
 * left-sidebar nav button for Arqueo (F10.1 routed-page remnant) was
 * removed in F11.3: the right-side MiTurnoPanel is the canonical
 * per-turn action surface.
 *
 * Zero-state contract (REQ-OPS-187, DA-F12.1-4): when `uuid_sesion` is
 * `null` OR the SWR data has not populated, the panel renders
 * all-zero KPIs without skeleton / error UI. The hook's `emptyMiTurno`
 * fallback enforces this at the data layer. The two action buttons are
 * disabled while `uuid_sesion === null` (no actionable state).
 */
import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import { totalCobradoFromMiTurno } from '../types';
import { useMiTurno } from '../hooks/useMiTurno';
import { ArqueoButton } from './ArqueoButton';
import { CerrarTurnoButton } from './CerrarTurnoButton';
import { MiTurnoKpiCard } from './MiTurnoKpiCard';

export interface MiTurnoPanelProps {
  /**
   * Active operator turno UUID. When `null` (no `useSesionActiva()`
   * resolution yet), the hook returns the all-zero fallback and the
   * panel renders zeros without skeleton / error UI.
   */
  uuid_sesion: string | null;
}

export function MiTurnoPanel({ uuid_sesion }: MiTurnoPanelProps): JSX.Element {
  const { t } = useTranslation('operacion');
  const { data, isStale } = useMiTurno(uuid_sesion);

  // The hook guarantees `data` is always non-null (zero-state fallback).
  // Defensive `?? 0` keeps the type narrow in case the SWR shape drifts.
  const ingresos = data?.ingresos_count ?? 0;
  const salidas = data?.salidas_count ?? 0;
  const totalCobrado = data ? totalCobradoFromMiTurno(data) : 0;
  const efectivo = data?.total_cobrado_efectivo_cop ?? 0;
  const datafono = data?.total_cobrado_datafono_cop ?? 0;

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
        <CardDescription className="sr-only">
          {t('miTurno.kpis.totalCobrado')} + {t('miTurno.kpis.efectivo')} +{' '}
          {t('miTurno.kpis.datafono')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 p-2">
        <div className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
          <MiTurnoKpiCard
            labelKey="miTurno.kpis.ingresos"
            value={ingresos}
            testIdSlug="ingresos"
          />
          <MiTurnoKpiCard
            labelKey="miTurno.kpis.salidas"
            value={salidas}
            testIdSlug="salidas"
          />
          <MiTurnoKpiCard
            labelKey="miTurno.kpis.totalCobrado"
            value={totalCobrado}
            testIdSlug="total-cobrado"
            unitKey="miTurno.unidades.cop"
          />
          <MiTurnoKpiCard
            labelKey="miTurno.kpis.efectivo"
            value={efectivo}
            testIdSlug="efectivo"
            unitKey="miTurno.unidades.cop"
          />
          <MiTurnoKpiCard
            labelKey="miTurno.kpis.datafono"
            value={datafono}
            testIdSlug="datafono"
            unitKey="miTurno.unidades.cop"
          />
        </div>
        <div className="flex gap-2">
          <ArqueoButton uuid_sesion={uuid_sesion} />
          <CerrarTurnoButton uuid_sesion={uuid_sesion} />
        </div>
      </CardContent>
    </Card>
  );
}