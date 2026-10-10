/**
 * `<AlertasList />` -- HU-F19.5 "bandeja de alertas" container.
 *
 * Scope: alertas across the ACTOR's `sucursales permitidas`
 * (`useAdminAuth().sucursalUuids`), cross-branch like `/pairing` and
 * `/arqueos` (so it sits in `App.tsx`'s global route group, outside
 * `<RequireSucursal>` -- see that file's routing comment).
 *
 * Defense in depth on the branch scope: the sucursal filter dropdown
 * only ever offers the actor's permitted branches (never the full
 * directory), AND the fetched `items` are filtered client-side to that
 * same permitted set before rendering -- mirrors the "fast-fail
 * Pydantic validator + endpoint-layer DB check" two-layer pattern this
 * repo uses server-side (`schemas/workflows.py::ReclamosCreate`
 * docblock). If the BE's `GET /workflows/alerta` ever returns a row
 * outside the actor's permitted branches, this screen still won't show
 * it.
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAdminAuth } from '@parkos/ui-kit/hooks';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/layout/PageHeader';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import { AlertasFilters, type AlertasFiltersValue } from '../components/AlertasFilters';
import { AlertasTable } from '../components/AlertasTable';
import { useAlertasAdmin } from '../hooks/useAlertasAdmin';
import { ALERTA_ESTADOS, ALERTA_SEVERITIES } from '../api/alertasSchema';
import type { AlertaRead, AlertasListQuery } from '../api/alertasSchema';
import { useUrlFilters } from '@/lib/useUrlFilters';

const EMPTY_FILTERS: AlertasFiltersValue = {
  uuid_sucursal: '',
  tipo_alerta: '',
  estado: '',
  severidad: '',
  desde: '',
  hasta: '',
};

function buildQuery(filters: AlertasFiltersValue): AlertasListQuery {
  const query: AlertasListQuery = { limit: 20 };
  if (filters.uuid_sucursal) query.uuid_sucursal = filters.uuid_sucursal;
  if (filters.tipo_alerta) query.tipo_alerta = filters.tipo_alerta;
  if (filters.estado) query.estado = filters.estado;
  if (filters.severidad) query.severidad = filters.severidad;
  if (filters.desde) query.desde = filters.desde;
  if (filters.hasta) query.hasta = filters.hasta;
  return query;
}

export interface AlertasListPageProps {
  /** Test-only hook to isolate the SWR cache across cases (mirrors useArqueosAdmin's swrSalt). */
  swrSalt?: string;
}

export default function AlertasList({ swrSalt }: AlertasListPageProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { sucursalUuids } = useAdminAuth();
  const { sucursales } = useSucursalesDirectorio();

  // Filters live in the querystring so "Volver" from a detail restores them.
  const [filters, setFilters] = useUrlFilters<AlertasFiltersValue>(EMPTY_FILTERS, {
    sanitize: (v) => ({
      ...v,
      estado: (ALERTA_ESTADOS as readonly string[]).includes(v.estado) ? v.estado : '',
      severidad: (ALERTA_SEVERITIES as readonly string[]).includes(v.severidad) ? v.severidad : '',
    }),
  });
  const query = useMemo(() => buildQuery(filters), [filters]);
  const { items, isLoading, error, hasMore, loadMore } = useAlertasAdmin(query, { swrSalt });

  const permittedSet = useMemo(() => new Set(sucursalUuids), [sucursalUuids]);
  const sucursalOptions = useMemo(
    () => sucursales.filter((s) => permittedSet.has(s.uuid)).map((s) => ({ uuid: s.uuid, nombre: s.nombre })),
    [sucursales, permittedSet],
  );
  const scopedItems = useMemo(
    () => items.filter((item) => item.uuid_sucursal !== null && permittedSet.has(item.uuid_sucursal)),
    [items, permittedSet],
  );

  function handleOpen(alerta: AlertaRead): void {
    // `severity` isn't carried by the detail screen's own GET (see
    // `AlertaDetalle.tsx`'s docblock) -- forward it as a best-effort
    // router-state hint so a click-through from this list shows it
    // immediately instead of "—" until proven otherwise.
    navigate(`/alertas/${alerta.uuid}`, { state: { severity: alerta.severity } });
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="alertas-page"
    >
      <PageHeader
        title={t('alertas.title', 'Alertas')}
        subtitle={t(
          'alertas.subtitle',
          'Bandeja cross-branch de alertas de las sucursales a tu cargo, con severidad y estado.',
        )}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('alertas.filters.title', 'Filtros')}</CardTitle>
        </CardHeader>
        <CardContent>
          <AlertasFilters
            value={filters}
            onChange={setFilters}
            onReset={() => setFilters(EMPTY_FILTERS)}
            options={{ sucursalOptions }}
          />
        </CardContent>
      </Card>

      {error !== undefined && (
        <div
          role="alert"
          data-testid="alertas-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('alertas.errorLoading', 'No se pudieron cargar las alertas.')}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('alertas.listTitle', 'Resultados')}</CardTitle>
        </CardHeader>
        <CardContent>
          <AlertasTable
            items={scopedItems}
            isLoading={isLoading && scopedItems.length === 0}
            hasMore={hasMore}
            onLoadMore={() => {
              void loadMore();
            }}
            onOpen={handleOpen}
          />
        </CardContent>
      </Card>
    </main>
  );
}
