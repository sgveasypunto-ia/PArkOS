/**
 * `<BuscarGlobal />` -- HU-F20.4 bounded bitácora typeahead (<=10
 * results). Debounced 300ms against `GET /admin/log-transaccional/buscar`
 * (see `hooks/useBuscarLogTransaccional.ts`). Selecting a result
 * navigates to `LogTransaccional.tsx` filtered by that row's
 * `uuid_registro_afectado` (`?uuid_registro=`).
 */
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

import { useBuscarLogTransaccional } from '../hooks/useBuscarLogTransaccional';
import type { BuscarPrefijoItem } from '../api/auditoriaSchema';

export default function BuscarGlobal(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { prefijo, setPrefijo, items, isLoading, error } = useBuscarLogTransaccional();

  function handleSelect(item: BuscarPrefijoItem): void {
    if (!item.uuid_registro_afectado) return;
    navigate(`/auditoria/log?uuid_registro=${item.uuid_registro_afectado}`);
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 p-4 md:p-6 lg:p-8"
      data-testid="buscar-global-page"
    >
      <PageHeader
        title={t('auditoria.buscar.title', 'Búsqueda global')}
        subtitle={t(
          'auditoria.buscar.subtitle',
          'Typeahead acotado (máx. 10 resultados) sobre tabla y registro afectado.',
        )}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t('auditoria.buscar.formTitle', 'Buscar')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input
            data-testid="buscar-global-input"
            value={prefijo}
            onChange={(e) => setPrefijo(e.target.value)}
            placeholder={t('auditoria.buscar.placeholder', 'Prefijo (tabla o UUID de registro)')}
            aria-label={t('auditoria.buscar.placeholder', 'Prefijo (tabla o UUID de registro)')}
          />

          {error && (
            <p
              role="alert"
              data-testid="buscar-global-error"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error.message}
            </p>
          )}

          {isLoading && (
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {t('auditoria.buscar.loading', 'Buscando...')}
            </p>
          )}

          {!isLoading && prefijo.trim().length > 0 && items.length === 0 && !error && (
            <p
              role="status"
              aria-live="polite"
              data-testid="buscar-global-empty"
              className="text-sm text-muted-foreground"
            >
              {t('auditoria.buscar.empty', 'Sin resultados para ese prefijo.')}
            </p>
          )}

          {items.length > 0 && (
            <ul data-testid="buscar-global-results" className="divide-y rounded-md border">
              {items.map((item) => (
                <li key={item.uuid}>
                  <button
                    type="button"
                    data-testid={`buscar-global-result-${item.uuid}`}
                    onClick={() => handleSelect(item)}
                    disabled={!item.uuid_registro_afectado}
                    className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-muted/40 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="font-medium">{item.tabla_afectada ?? '—'}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {item.uuid_registro_afectado ?? '—'} · {item.timestamp_evento}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
