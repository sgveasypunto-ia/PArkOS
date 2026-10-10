/**
 * `<ReclamosList />` -- HU-F20.3 "reclamos" inbox. Mirrors
 * `AnulacionesList.tsx` 1:1.
 */
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { EstadoReclamoBadge } from '../components/EstadoReclamoBadge';
import { useReclamosAdmin } from '../hooks/useReclamosAdmin';
import type { ReclamoRead } from '../api/reclamosSchema';

export interface ReclamosListPageProps {
  /** Test-only hook to isolate the SWR cache across cases. */
  swrSalt?: string;
}

export default function ReclamosList({ swrSalt }: ReclamosListPageProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { items, isLoading, error, hasMore, loadMore } = useReclamosAdmin({ swrSalt });

  function handleOpen(reclamo: ReclamoRead): void {
    navigate(`/reclamos/${reclamo.uuid}`);
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="reclamos-page"
    >
      <PageHeader
        title={t('reclamos.title', 'Reclamos')}
        subtitle={t(
          'reclamos.subtitle',
          'Bandeja cross-branch de reclamos sobre ingresos, salidas y facturas, con su estado actual.',
        )}
      />

      {error !== undefined && (
        <div
          role="alert"
          data-testid="reclamos-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('reclamos.errorLoading', 'No se pudieron cargar los reclamos.')}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('reclamos.listTitle', 'Resultados')}</CardTitle>
        </CardHeader>
        <CardContent>
          {!isLoading && items.length === 0 ? (
            <div
              role="status"
              aria-live="polite"
              data-testid="reclamos-empty"
              className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
            >
              {t('reclamos.empty', 'No hay reclamos registrados.')}
            </div>
          ) : (
            <div className="space-y-3">
              <table
                data-testid="reclamos-table"
                className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
              >
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('reclamos.table.fecha', 'Fecha')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('reclamos.table.sucursal', 'Sucursal')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('reclamos.table.tipo', 'Tipo')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('reclamos.table.estado', 'Estado')}
                    </th>
                    <th scope="col" className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((reclamo) => (
                    <tr
                      key={reclamo.uuid}
                      data-testid={`reclamos-row-${reclamo.uuid}`}
                      className="border-t hover:bg-muted/20"
                    >
                      <td className="px-3 py-2 font-mono text-xs">
                        {reclamo.timestamp_evento ?? reclamo.created_at}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{reclamo.uuid_sucursal ?? '—'}</td>
                      <td className="px-3 py-2 text-xs">{reclamo.tipo_reclamable ?? '—'}</td>
                      <td className="px-3 py-2">
                        <EstadoReclamoBadge estado={reclamo.estado} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleOpen(reclamo)}
                          data-testid={`reclamos-row-open-${reclamo.uuid}`}
                        >
                          {t('reclamos.table.openButton', 'Ver detalle')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {hasMore && (
                <div className="flex justify-center">
                  <Button
                    data-testid="reclamos-load-more"
                    type="button"
                    variant="outline"
                    onClick={() => {
                      void loadMore();
                    }}
                  >
                    {t('reclamos.table.loadMore', 'Cargar más')}
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
