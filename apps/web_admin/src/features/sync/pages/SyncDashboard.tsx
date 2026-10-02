/**
 * `<SyncDashboard />` — HU-F19.2 sync monitoring dashboard (web_admin),
 * mounted at `/sync`. Cross-branch by nature (same reasoning as
 * `/pairing` and the reportería heatmap): shows every sucursal the
 * admin can see at once, so it sits OUTSIDE `<RequireSucursal>` in
 * `App.tsx`.
 *
 * Hosts the outer `<Tabs>` shell for the 3 HU-F19.2 screens (same dual
 * role `Reporteria.tsx` plays for its own 3 tabs): this page IS both
 * "the heatmap + resumen tab content" and "the container for the Log /
 * Conflictos tabs". Clicking a heatmap branch row drills down to the
 * Log tab pre-filtered by that `uuid_sucursal` (lifted `selectedSucursal`
 * + `tab` state).
 *
 * The verde/amarillo/rojo resumen counts and the `estado` badges are
 * rendered straight from `/admin/sync/estado` (BR1) -- never
 * recomputed client-side (see `syncSchema.ts`'s docstring).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { HeatmapOcupacion } from '@/components/charts/HeatmapOcupacion';

import { useSyncEstado, useSyncHeatmap } from '../hooks/useSync';
import { SyncMissingSucursalContextError } from '../api/syncApi';
import type { SyncEstadoColor } from '../api/syncSchema';
import SyncLog from './SyncLog';
import SyncConflict from './SyncConflict';
import ValidacionEventos from './ValidacionEventos';

export default function SyncDashboard(): JSX.Element {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'dashboard' | 'log' | 'conflictos' | 'validacion-eventos'>(
    'dashboard',
  );
  const [selectedSucursal, setSelectedSucursal] = useState<string | null>(null);

  const estado = useSyncEstado();
  const heatmap = useSyncHeatmap();

  const resumen = useMemo(() => {
    const counts: Record<SyncEstadoColor, number> = { verde: 0, amarillo: 0, rojo: 0 };
    for (const item of estado.data?.items ?? []) {
      counts[item.estado] += 1;
    }
    return counts;
  }, [estado.data]);

  const sinSucursales =
    estado.error instanceof SyncMissingSucursalContextError ||
    (estado.data !== undefined && estado.data.items.length === 0);

  function handleHeatmapRowClick(uuid: string): void {
    setSelectedSucursal(uuid);
    setTab('log');
  }

  return (
    <main className="min-h-screen bg-background p-6" data-testid="page-sync-dashboard">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        <header className="border-b pb-4">
          <h1 className="text-3xl font-bold tracking-tight">
            {t('sync.title', 'Sincronización')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t(
              'sync.subtitle',
              'Estado de sincronización de todas las sucursales, histórico y conflictos.',
            )}
          </p>
        </header>

        <Tabs value={tab} onValueChange={(value) => setTab(value as typeof tab)}>
          <TabsList aria-label={t('sync.tabsLabel', 'Sección de sincronización')}>
            <TabsTrigger value="dashboard" data-testid="sync-tab-dashboard">
              {t('sync.tabs.dashboard', 'Dashboard')}
            </TabsTrigger>
            <TabsTrigger value="log" data-testid="sync-tab-log">
              {t('sync.tabs.log', 'Log')}
            </TabsTrigger>
            <TabsTrigger value="conflictos" data-testid="sync-tab-conflictos">
              {t('sync.tabs.conflictos', 'Conflictos')}
            </TabsTrigger>
            <TabsTrigger value="validacion-eventos" data-testid="sync-tab-validacion-eventos">
              {t('sync.tabs.validacionEventos', 'Validación de eventos')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="dashboard">
            <div className="flex flex-col gap-4">
              {sinSucursales ? (
                <p
                  role="status"
                  aria-live="polite"
                  data-testid="sync-dashboard-empty"
                  className="rounded-md border bg-muted/40 p-4 text-sm text-muted-foreground"
                >
                  {t('sync.empty', 'Sin sucursales sincronizando aún')}
                </p>
              ) : (
                <>
                  <section
                    aria-label={t('sync.resumen.label', 'Resumen de estado')}
                    className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/20 p-4"
                    data-testid="sync-resumen"
                  >
                    <Badge variant="success" data-testid="sync-resumen-verde">
                      {t('sync.resumen.verde', '{{count}} verde', { count: resumen.verde })}
                    </Badge>
                    <Badge variant="warning" data-testid="sync-resumen-amarillo">
                      {t('sync.resumen.amarillo', '{{count}} amarillo', {
                        count: resumen.amarillo,
                      })}
                    </Badge>
                    <Badge variant="destructive" data-testid="sync-resumen-rojo">
                      {t('sync.resumen.rojo', '{{count}} rojo', { count: resumen.rojo })}
                    </Badge>
                  </section>

                  <div className="rounded-lg border bg-card p-4" data-testid="sync-heatmap-section">
                    {heatmap.error ? (
                      <p
                        role="alert"
                        aria-live="assertive"
                        data-testid="sync-heatmap-error"
                        className="text-sm text-destructive"
                      >
                        {heatmap.error.message}
                      </p>
                    ) : (
                      <HeatmapOcupacion
                        data={heatmap.data}
                        sucursales={heatmap.sucursales}
                        title={t('sync.heatmap.title', 'Lag de sincronización por hora (24h, UTC)')}
                        valueUnitLabel={t('sync.heatmap.unit', 'seg de lag')}
                        footerNote={t(
                          'sync.heatmap.footer',
                          'Lag estimado por ciclo de sync (segundos) -- reconstruido desde el histórico, no reclasifica verde/amarillo/rojo (ver resumen arriba).',
                        )}
                        emptyMessage={t('sync.empty', 'Sin sucursales sincronizando aún')}
                        onRowClick={handleHeatmapRowClick}
                      />
                    )}
                  </div>
                </>
              )}
            </div>
          </TabsContent>

          <TabsContent value="log">
            <SyncLog
              initialUuidSucursal={selectedSucursal}
              onUuidSucursalChange={setSelectedSucursal}
            />
          </TabsContent>

          <TabsContent value="conflictos">
            <SyncConflict initialUuidSucursal={selectedSucursal} />
          </TabsContent>

          <TabsContent value="validacion-eventos">
            <ValidacionEventos initialUuidSucursal={selectedSucursal} />
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}
