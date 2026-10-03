/**
 * ``<ArqueosPage />`` -- container (HU-F18.2).
 *
 * Owns the page state, SWR cache key composition, and the
 * container/presentational split. Sub-components:
 *
 *   - ``<ArqueosFilters />``  -- 4-field filter bar.
 *   - ``<ArqueosList />``     -- cursor-paginated table.
 *   - ``<ArqueoDetalle />``   -- selected-row detail with DiferenciasPanel.
 *
 * State held in this file (per AGENTS.md RHF / SWR separation):
 *
 *   - ``filters``: ArqueosFiltersValue (the four controlled inputs).
 *   - ``selectedArqueo``: row the operator clicked (drives detail).
 *   - ``cursor``: cursor for the next page; ``null`` after a successful
 *     page that returned `items=[]` (EOF) or no previous response.
 *
 * On mount: SWR by default (no filters, limit 20) returns the most-
 * recent 20 across every branch. Operators narrow from there.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueries } from '@tanstack/react-query';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
import { listCatalog } from '@/features/catalogos/api/catalogApi';

import {
  ArqueosFilters,
  type ArqueosFiltersValue,
  type ArqueosFiltersOptions,
} from '../components/ArqueosFilters';
import { ArqueosList } from '../components/ArqueosList';
import { ArqueoDetalle } from '../components/ArqueoDetalle';
import { ArqueosResumen } from '../components/ArqueosResumen';
import {
  useArqueosAdmin,
  type UseArqueosAdminReturn,
} from '../hooks/useArqueosAdmin';
import { useArqueoDetalle } from '../hooks/useArqueoDetalle';
import type {
  ArqueoRead,
  ArqueosListQuery,
} from '../api/arqueosSchema';

const EMPTY_FILTERS: ArqueosFiltersValue = {
  uuid_sucursal: '',
  fecha_desde: '',
  fecha_hasta: '',
  uuid_tipo_arqueo: '',
};

function buildQuery(filters: ArqueosFiltersValue): ArqueosListQuery {
  const query: ArqueosListQuery = { limit: 20 };
  if (filters.uuid_sucursal) query.uuid_sucursal = filters.uuid_sucursal;
  if (filters.fecha_desde) query.fecha_desde = filters.fecha_desde;
  if (filters.fecha_hasta) query.fecha_hasta = filters.fecha_hasta;
  if (filters.uuid_tipo_arqueo) query.uuid_tipo_arqueo = filters.uuid_tipo_arqueo;
  return query;
}

export function ArqueosPage(): JSX.Element {
  const { t } = useTranslation();
  const [filters, setFilters] = useState<ArqueosFiltersValue>(EMPTY_FILTERS);
  const [selectedArqueo, setSelectedArqueo] = useState<ArqueoRead | null>(
    null,
  );

  const query = useMemo(() => buildQuery(filters), [filters]);
  const {
    items,
    isLoading,
    error,
    hasMore,
    loadMore,
  } = useArqueosAdmin(query) as UseArqueosAdminReturn;

  const { diferencias, isLoading: diferenciasLoading, error: diferenciasError } =
    useArqueoDetalle(selectedArqueo?.uuid ?? null);

  // Filter options for the dropdowns. The two reference catalogs
  // (``sucursales`` and ``tipo_arqueo``) have their own authenticated
  // API clients in the shared layer (``parkosFetchRaw`` -- Bearer JWT +
  // X-Sucursal-Context); we use ``useQueries`` here for the cache
  // isolation rules. The shape of the result maps into our dropdowns.
  //
  // Bugfix (QA batch Arqueos, 2026-10-02): both dropdowns used to be
  // permanently empty. The sucursal query called the raw unauthenticated
  // ``fetch('/api/v1/sucursales', { credentials: 'include' })`` -- this
  // app authenticates via a Bearer JWT from the Zustand auth store, NOT
  // cookies, so the request always 401'd and silently swallowed the
  // error (`if (!res.ok) return []`). The tipo_arqueo query hit
  // ``/api/v1/admin/caja``, which does not exist (404) -- the real
  // catalog is ``GET /api/v1/catalogos/tipo-arqueo`` (mirrors
  // electron-sucursal's ``useTipoArqueoPorCodigo`` hook). Both now reuse
  // the same authenticated API clients the rest of web_admin uses.
  const [sucursalesQ, tiposQ] = useQueries({
    queries: [
      {
        queryKey: ['arqueo-filter-sucursales'],
        queryFn: async (): Promise<Array<{ uuid: string; nombre: string | null }>> => {
          const rows = await listSucursales({ limit: 200 });
          return rows.map((s) => ({ uuid: s.uuid, nombre: s.nombre }));
        },
      },
      {
        queryKey: ['arqueo-filter-tipos'],
        queryFn: async (): Promise<Array<{ uuid: string; codigo: string | null }>> => {
          const rows = await listCatalog('tipo-arqueo');
          return rows.map((r) => ({
            uuid: r.uuid,
            codigo: typeof r.codigo === 'string' ? r.codigo : null,
          }));
        },
      },
    ],
  });

  // Re-focus the detail panel on a fresh row.
  useEffect(() => {
    /* no-op -- the hook handles re-fetch on uuid change */
  }, [selectedArqueo?.uuid]);

  const filterOptions: ArqueosFiltersOptions = {
    sucursalOptions: sucursalesQ.data ?? [],
    tipoOptions: tiposQ.data ?? [],
  };

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="arqueos-page">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">
          {t('arqueos.title', 'Arqueos')}
        </h1>
        <p className="text-muted-foreground text-sm">
          {t('arqueos.subtitle', 'Listado admin cross-branch de arqueos con filtros por sucursal, fecha y tipo.')}
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {t('arqueos.filters.title', 'Filtros')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ArqueosFilters
            value={filters}
            onChange={setFilters}
            onReset={() => setFilters(EMPTY_FILTERS)}
            options={filterOptions}
          />
        </CardContent>
      </Card>

      {error && (
        <div
          role="alert"
          data-testid="arqueos-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('arqueos.errorLoading', 'No se pudieron cargar los arqueos.')}
        </div>
      )}

      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list" data-testid="arqueos-tab-list-trigger">
            {t('arqueos.tabList', 'Listado')}
          </TabsTrigger>
          <TabsTrigger value="resumen" data-testid="arqueos-tab-resumen-trigger">
            {t('arqueos.tabResumen', 'Resumen')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {t('arqueos.listTitle', 'Resultados')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ArqueosList
                items={items}
                isLoading={isLoading && items.length === 0}
                hasMore={hasMore}
                isLoadingMore={false}
                onLoadMore={() => {
                  void loadMore();
                }}
                onSelect={setSelectedArqueo}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="resumen" className="mt-4">
          <ArqueosResumen />
        </TabsContent>
      </Tabs>

      <ArqueoDetalle
        arqueo={selectedArqueo}
        diferenciasLoading={diferenciasLoading}
        diferenciasError={diferenciasError}
        diferencias={diferencias}
        onClose={() => setSelectedArqueo(null)}
      />
    </main>
  );
}