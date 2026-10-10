/**
 * `<DianCola />` -- HU-F20.5 "monitor de envíos DIAN": cola, reintento y
 * revocación (revocación is OUT of scope here -- see the module docblock
 * on `DianDetalle.tsx` for why no "Anular" action exists in this slice).
 *
 * Cross-branch like `/alertas`, `/sync` and `/pairing` (same reasoning:
 * an admin monitors DIAN sends across every sucursal they're allowed to
 * see, not just the one active in the topbar), so it lives in `App.tsx`'s
 * global route group, outside `<RequireSucursal>`.
 *
 * Tabs: one per real `estado` value (`ENVIO_DIAN_ESTADOS`, confirmed by
 * reading `cloud_router.py::_ENVIO_DIAN_ESTADOS` -- NOT the 4-value
 * domain plan.md's HU-F13.4 BR2 describes, which is drift; see
 * `envioDianSchema.ts`'s docblock), plus "Todos". Each tab issues its
 * OWN server-filtered, cursor-paginated `GET /envio-dian?estado=...`
 * query (`useEnvioDianAdmin`) -- the listing itself is always accurate.
 *
 * Resumen counters: UNLIKE `/sync`'s verde/amarillo/rojo resumen (backed
 * by a dedicated aggregate endpoint, `sync_estado_agregado`), there is no
 * aggregate endpoint for `envio_dian`. The resumen here is computed
 * client-side (`buildEnvioDianCounts`) over a SEPARATE, unfiltered,
 * most-recent-N window (`limit: 100`) -- a best-effort snapshot, not a
 * true total, and labeled as such in the UI copy so it never overstates
 * its own precision.
 */
import { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/layout/PageHeader';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';

import { ENVIO_DIAN_ESTADOS, type EnvioDianEstado, type EnvioDianRead } from '../api/envioDianSchema';
import { useEnvioDianAdmin } from '../hooks/useEnvioDianAdmin';
import { useRetryEnvioDian } from '../hooks/useRetryEnvioDian';
import { buildEnvioDianCounts } from '../lib/envioDianCounts';
import { DianQueueTable } from '../components/DianQueueTable';

const RESUMEN_WINDOW_LIMIT = 100;
const TAB_PAGE_LIMIT = 50;
type DianTab = 'todos' | EnvioDianEstado;

export interface DianColaPageProps {
  /** Test-only hook to isolate the SWR cache across cases (mirrors AlertasList's swrSalt). */
  swrSalt?: string;
}

export default function DianCola({ swrSalt }: DianColaPageProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // The active tab lives in the querystring so "Volver" from the detail
  // (history back) lands on the same tab (PT-1).
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get('estado');
  const tab: DianTab =
    rawTab !== null && (ENVIO_DIAN_ESTADOS as readonly string[]).includes(rawTab)
      ? (rawTab as EnvioDianEstado)
      : 'todos';
  const setTab = (next: DianTab): void => {
    const params = new URLSearchParams(searchParams);
    if (next === 'todos') params.delete('estado');
    else params.set('estado', next);
    setSearchParams(params, { replace: true });
  };

  const resumenQuery = useMemo(() => ({ limit: RESUMEN_WINDOW_LIMIT }), []);
  const resumen = useEnvioDianAdmin(resumenQuery, { swrSalt: swrSalt ? `${swrSalt}-resumen` : undefined });
  const counts = useMemo(() => buildEnvioDianCounts(resumen.items), [resumen.items]);

  const tabQuery = useMemo(
    () => ({ estado: tab === 'todos' ? undefined : tab, limit: TAB_PAGE_LIMIT }),
    [tab],
  );
  const queue = useEnvioDianAdmin(tabQuery, { swrSalt });

  const { trigger, isRetrying } = useRetryEnvioDian();

  function handleOpen(envio: EnvioDianRead): void {
    // No single-item GET exists for envio_dian (see `useEnvioDianChain`'s
    // docblock) -- the full row is forwarded via router `state` since a
    // direct deep-link/refresh of `<DianDetalle />` has no other way to
    // recover it. Documented known gap, same shape as `AlertasList`
    // forwarding `severity` for `<AlertaDetalle />`.
    navigate(`/dian/${envio.uuid}`, { state: { envio } });
  }

  async function handleRetry(envio: EnvioDianRead): Promise<void> {
    if (envio.uuid_factura_electronica === null) return;
    await trigger(envio.uuid_factura_electronica);
    await Promise.all([queue.refresh(), resumen.refresh()]);
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="dian-cola-page"
    >
      <PageHeader
        title={t('dian.title', 'Monitor de envíos DIAN')}
        subtitle={t(
          'dian.subtitle',
          'Cola de envíos a la DIAN de todas tus sucursales, con reintento de los rechazados.',
        )}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('dian.resumen.title', 'Resumen (ventana reciente)')}</CardTitle>
        </CardHeader>
        <CardContent>
          <section
            aria-label={t('dian.resumen.label', 'Resumen de estado')}
            className="flex flex-wrap items-center gap-3"
            data-testid="dian-resumen"
          >
            {ENVIO_DIAN_ESTADOS.map((estado) => (
              <Badge key={estado} variant="outline" data-testid={`dian-resumen-${estado}`}>
                {t(`dian.estado.${estado === 'en_proceso' ? 'enProceso' : estado}`, estado)}
                {': '}
                {counts[estado]}
              </Badge>
            ))}
          </section>
          <p className="text-muted-foreground mt-2 text-xs">
            {t(
              'dian.resumen.footnote',
              'Conteo sobre los {{limit}} envíos más recientes (no hay endpoint de agregado para esta tabla) -- no es un total histórico.',
              { limit: RESUMEN_WINDOW_LIMIT },
            )}
          </p>
        </CardContent>
      </Card>

      {queue.error !== undefined && (
        <div
          role="alert"
          data-testid="dian-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('dian.errorLoading', 'No se pudieron cargar los envíos DIAN.')}
        </div>
      )}

      <Card>
        <CardContent className="pt-6">
          <Tabs value={tab} onValueChange={(value) => setTab(value as DianTab)}>
            <TabsList aria-label={t('dian.tabsLabel', 'Estado del envío')} className="flex-wrap">
              <TabsTrigger value="todos" data-testid="dian-tab-todos">
                {t('dian.tabs.todos', 'Todos')}
              </TabsTrigger>
              {ENVIO_DIAN_ESTADOS.map((estado) => (
                <TabsTrigger key={estado} value={estado} data-testid={`dian-tab-${estado}`}>
                  {t(`dian.estado.${estado === 'en_proceso' ? 'enProceso' : estado}`, estado)}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value={tab}>
              <DianQueueTable
                items={queue.items}
                isLoading={queue.isLoading && queue.items.length === 0}
                hasMore={queue.hasMore}
                onLoadMore={() => {
                  void queue.loadMore();
                }}
                onOpen={handleOpen}
                onRetry={(envio) => {
                  void handleRetry(envio);
                }}
                isRetrying={isRetrying}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </main>
  );
}
