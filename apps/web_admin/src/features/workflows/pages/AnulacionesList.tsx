/**
 * `<AnulacionesList />` -- HU-F20.3 "anulaciones" inbox. Cross-branch
 * cursor-paginated table, no filter bar (the BE list endpoint only
 * supports `cursor`/`limit` -- see `useAnulacionesAdmin.ts`'s docblock).
 * Row click navigates to `/anulaciones/:uuid`.
 */
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { EstadoAnulacionBadge } from '../components/EstadoAnulacionBadge';
import { useAnulacionesAdmin } from '../hooks/useAnulacionesAdmin';
import type { AnulacionRead } from '../api/anulacionesSchema';

export interface AnulacionesListPageProps {
  /** Test-only hook to isolate the SWR cache across cases. */
  swrSalt?: string;
}

export default function AnulacionesList({ swrSalt }: AnulacionesListPageProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { items, isLoading, error, hasMore, loadMore } = useAnulacionesAdmin({ swrSalt });

  function handleOpen(anulacion: AnulacionRead): void {
    navigate(`/anulaciones/${anulacion.uuid}`);
  }

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid="anulaciones-page">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">{t('anulaciones.title', 'Anulaciones')}</h1>
        <p className="text-muted-foreground text-sm">
          {t(
            'anulaciones.subtitle',
            'Bandeja cross-branch de anulaciones de ingresos y salidas, con su estado actual.',
          )}
        </p>
      </header>

      {error !== undefined && (
        <div
          role="alert"
          data-testid="anulaciones-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('anulaciones.errorLoading', 'No se pudieron cargar las anulaciones.')}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('anulaciones.listTitle', 'Resultados')}</CardTitle>
        </CardHeader>
        <CardContent>
          {!isLoading && items.length === 0 ? (
            <div
              role="status"
              aria-live="polite"
              data-testid="anulaciones-empty"
              className="rounded-md border border-dashed bg-muted/30 px-3 py-6 text-center text-sm text-muted-foreground"
            >
              {t('anulaciones.empty', 'No hay anulaciones registradas.')}
            </div>
          ) : (
            <div className="space-y-3">
              <table
                data-testid="anulaciones-table"
                className="w-full overflow-x-auto rounded-lg border bg-card text-sm"
              >
                <thead className="bg-muted/40 text-left">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('anulaciones.table.fecha', 'Fecha')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('anulaciones.table.sucursal', 'Sucursal')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('anulaciones.table.tipo', 'Tipo')}
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      {t('anulaciones.table.estado', 'Estado')}
                    </th>
                    <th scope="col" className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((anulacion) => (
                    <tr
                      key={anulacion.uuid}
                      data-testid={`anulaciones-row-${anulacion.uuid}`}
                      className="border-t hover:bg-muted/20"
                    >
                      <td className="px-3 py-2 font-mono text-xs">
                        {anulacion.timestamp_evento ?? anulacion.created_at}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {anulacion.uuid_sucursal ?? '—'}
                      </td>
                      <td className="px-3 py-2 text-xs">{anulacion.tipo_anulable ?? '—'}</td>
                      <td className="px-3 py-2">
                        <EstadoAnulacionBadge estado={anulacion.estado} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => handleOpen(anulacion)}
                          data-testid={`anulaciones-row-open-${anulacion.uuid}`}
                        >
                          {t('anulaciones.table.openButton', 'Ver detalle')}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {hasMore && (
                <div className="flex justify-center">
                  <Button
                    data-testid="anulaciones-load-more"
                    type="button"
                    variant="outline"
                    onClick={() => {
                      void loadMore();
                    }}
                  >
                    {t('anulaciones.table.loadMore', 'Cargar más')}
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
