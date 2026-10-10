/**
 * `<LogTransaccional />` -- HU-F20.4 cross-branch bitácora listing
 * container. Mirrors `arqueos/pages/ArqueosPage.tsx` /
 * `alertas/pages/AlertasList.tsx` (filters own state, SWR cursor
 * pagination via `useLogTransaccional`, row click opens `LogDetalle`).
 *
 * Routing note: there is no `GET /admin/log-transaccional/{uuid}`
 * single-item endpoint in the HU-F20.4 contract (only list, verify-chain,
 * buscar) -- `LogDetalle` is reached via
 * `navigate(..., { state: { item } })` carrying the already-fetched row,
 * same pattern as `alertas/pages/AlertasList.tsx` forwarding `severity`
 * via router state. A direct/refreshed deep-link to `/auditoria/log/:uuid`
 * with no state shows a "volver al listado" fallback (see `LogDetalle.tsx`).
 *
 * `uuid_registro` can be pre-filled from `?uuid_registro=` in the URL --
 * `BuscarGlobal.tsx` navigates here with that query param set when an
 * admin picks a typeahead result.
 *
 * `?uuid_alerta=` (QA backlog cleanup, 2026-10-02) is the entry point for
 * `<AlertaLink>` (`features/arqueos/components/AlertaLink.tsx`): an
 * arqueo's descuadre-crítico alerta is logged as its own
 * `log_transaccional` row (`tabla_afectada='alerta'`,
 * `uuid_registro_afectado=<alerta.uuid>` -- see
 * `repo/workflow.py::append_transition`), so pre-seeding
 * `tabla='alerta'` + `uuid_registro=<uuid_alerta>` lands the admin
 * directly on that alert's bitácora entry. Takes precedence over
 * `?uuid_registro=` when both are present (mutually exclusive in
 * practice -- different callers).
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useUrlFilters } from '@/lib/useUrlFilters';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/layout/PageHeader';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';

import {
  LogTransaccionalFilters,
  type LogTransaccionalFiltersValue,
} from '../components/LogTransaccionalFilters';
import { LogTransaccionalTable } from '../components/LogTransaccionalTable';
import { useLogTransaccional } from '../hooks/useLogTransaccional';
import type { AuditLogItem, LogTransaccionalListQuery } from '../api/auditoriaSchema';

function emptyFilters(
  uuidRegistro: string,
  tabla: string = '',
): LogTransaccionalFiltersValue {
  return {
    tabla,
    uuid_registro: uuidRegistro,
    uuid_sucursal: '',
    uuid_usuario: '',
    desde: '',
    hasta: '',
  };
}

function buildQuery(filters: LogTransaccionalFiltersValue): LogTransaccionalListQuery {
  const query: LogTransaccionalListQuery = { limit: 20 };
  if (filters.tabla) query.tabla = filters.tabla;
  if (filters.uuid_registro) query.uuid_registro = filters.uuid_registro;
  if (filters.uuid_sucursal) query.uuid_sucursal = filters.uuid_sucursal;
  if (filters.uuid_usuario) query.uuid_usuario = filters.uuid_usuario;
  if (filters.desde) query.desde = filters.desde;
  if (filters.hasta) query.hasta = filters.hasta;
  return query;
}

export interface LogTransaccionalProps {
  /** Test-only hook to isolate the SWR cache across cases (mirrors useArqueosAdmin's swrSalt). */
  swrSalt?: string;
}

export default function LogTransaccional({ swrSalt }: LogTransaccionalProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { sucursales } = useSucursalesDirectorio();

  // Filters live in the querystring (`?tabla=&uuid_registro=&...`) so the
  // detail's "Volver" (history back) restores them (PT-1). `?uuid_alerta=` is a
  // deep-link seed (tabla='alerta' + uuid_registro) dropped on the first edit.
  const [filters, setFilters] = useUrlFilters<LogTransaccionalFiltersValue>(emptyFilters(''), {
    seed: (params) => {
      const uuidAlerta = params.get('uuid_alerta');
      return uuidAlerta ? { tabla: 'alerta', uuid_registro: uuidAlerta } : null;
    },
    seedKeys: ['uuid_alerta'],
  });

  const query = useMemo(() => buildQuery(filters), [filters]);
  const { items, isLoading, error, hasMore, loadMore } = useLogTransaccional(query, { swrSalt });

  const sucursalOptions = useMemo(
    () => sucursales.map((s) => ({ uuid: s.uuid, nombre: s.nombre })),
    [sucursales],
  );

  function handleOpen(item: AuditLogItem): void {
    navigate(`/auditoria/log/${item.uuid}`, { state: { item } });
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="log-transaccional-page"
    >
      <PageHeader
        title={t('auditoria.title', 'Bitácora')}
        subtitle={t(
          'auditoria.subtitle',
          'Listado cross-branch de eventos de bitácora, con filtros por tabla, registro, sucursal, usuario y fecha.',
        )}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('auditoria.filters.title', 'Filtros')}</CardTitle>
        </CardHeader>
        <CardContent>
          <LogTransaccionalFilters
            value={filters}
            onChange={setFilters}
            onReset={() => setFilters(emptyFilters(''))}
            options={{ sucursalOptions }}
          />
        </CardContent>
      </Card>

      {error && (
        <div
          role="alert"
          data-testid="log-transaccional-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('auditoria.listTitle', 'Resultados')}</CardTitle>
        </CardHeader>
        <CardContent>
          <LogTransaccionalTable
            items={items}
            isLoading={isLoading && items.length === 0}
            hasMore={hasMore}
            isLoadingMore={false}
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
