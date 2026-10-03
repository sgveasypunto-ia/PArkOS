/**
 * `<LogDetalle />` -- HU-F20.4 single bitácora-event detail: renders
 * `datos_anteriores` vs `datos_nuevos` as a field-by-field plain-text
 * diff (mirrors the structure, not the whole-blob approach, of
 * `sync/pages/SyncConflict.tsx`'s local/cloud diff -- see
 * `lib/diffAuditLog.ts`'s own docblock for why), plus
 * `hash_anterior`/`hash_actual` via the shared `<HashChainStatus />`
 * badge (already reused by `arqueos/components/ArqueosList.tsx`).
 *
 * No `GET /admin/log-transaccional/{uuid}` endpoint exists in the
 * HU-F20.4 contract -- the row is received via `navigate(..., { state })`
 * from `LogTransaccional.tsx` (same router-state-carries-the-row pattern
 * as `alertas/pages/AlertasList.tsx` forwarding `severity`). A direct
 * visit/refresh with no state shows a "volver al listado" fallback
 * instead of fetching -- there is nothing to fetch BY.
 */
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { HashChainStatus } from '@/components/HashChainStatus';
import { formatBackendTimestampLocal } from '@/features/reporteria/components/dateRange';

import type { AuditLogItem } from '../api/auditoriaSchema';
import { diffAuditFields, stringifyAuditValue } from '../lib/diffAuditLog';

interface LogDetalleLocationState {
  item?: AuditLogItem;
}

export default function LogDetalle(): JSX.Element {
  const { t } = useTranslation();
  const { uuid } = useParams<{ uuid: string }>();
  const location = useLocation();
  const item = (location.state as LogDetalleLocationState | null)?.item ?? null;

  if (!item || item.uuid !== uuid) {
    return (
      <main className="space-y-4 p-4 md:p-6" data-testid="log-detalle-not-found">
        <p role="status" className="text-sm text-muted-foreground">
          {t(
            'auditoria.detail.notFound',
            'No se encontró el detalle de este evento (volvé al listado para abrirlo de nuevo).',
          )}
        </p>
        <Button asChild variant="outline" size="sm">
          <Link to="/auditoria/log" data-testid="log-detalle-back">
            {t('auditoria.detail.backToList', 'Volver al listado')}
          </Link>
        </Button>
      </main>
    );
  }

  const diffRows = diffAuditFields(item.datos_anteriores, item.datos_nuevos);

  return (
    <main className="space-y-4 p-4 md:p-6" data-testid={`log-detalle-${item.uuid}`}>
      <header className="flex items-center justify-between gap-3 rounded-md border bg-card px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            {t('auditoria.detail.title', 'Detalle de evento')}
          </h1>
          <p data-testid="log-detalle-meta" className="font-mono text-xs text-muted-foreground">
            {formatBackendTimestampLocal(item.timestamp_evento)} · {item.tabla_afectada ?? '—'} ·{' '}
            {item.accion ?? '—'}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/auditoria/log" data-testid="log-detalle-back">
            {t('auditoria.detail.backToList', 'Volver al listado')}
          </Link>
        </Button>
      </header>

      <dl className="grid grid-cols-1 gap-3 rounded-md border bg-card p-4 text-sm sm:grid-cols-2 md:grid-cols-3">
        <div>
          <dt className="text-xs font-medium text-muted-foreground">
            {t('auditoria.detail.uuid', 'UUID')}
          </dt>
          <dd className="font-mono text-xs">{item.uuid}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-muted-foreground">
            {t('auditoria.detail.sucursal', 'Sucursal')}
          </dt>
          <dd className="font-mono text-xs">{item.uuid_sucursal ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-muted-foreground">
            {t('auditoria.detail.usuario', 'Usuario')}
          </dt>
          <dd className="font-mono text-xs">{item.uuid_usuario ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs font-medium text-muted-foreground">
            {t('auditoria.detail.referencia', 'Referencia')}
          </dt>
          <dd className="font-mono text-xs">{item.uuid_referencia ?? '—'}</dd>
        </div>
        <div className="sm:col-span-2 md:col-span-2">
          <dt className="text-xs font-medium text-muted-foreground">
            {t('auditoria.detail.hashChain', 'Cadena de hashes')}
          </dt>
          <dd data-testid="log-detalle-hash">
            <HashChainStatus hashAnterior={item.hash_anterior} hashActual={item.hash_actual} />
          </dd>
        </div>
      </dl>

      <section data-testid="log-detalle-diff" aria-label={t('auditoria.detail.diffTitle', 'Diferencias')}>
        <h2 className="mb-2 text-sm font-semibold">
          {t('auditoria.detail.diffTitle', 'Diferencias')}
        </h2>
        {diffRows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t('auditoria.detail.diffEmpty', 'Este evento no registró datos antes/después.')}
          </p>
        ) : (
          <table className="w-full overflow-x-auto rounded-lg border bg-card text-sm">
            <thead className="bg-muted/40 text-left">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t('auditoria.detail.field', 'Campo')}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t('auditoria.detail.before', 'Antes')}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t('auditoria.detail.after', 'Después')}
                </th>
              </tr>
            </thead>
            <tbody>
              {diffRows.map((row) => (
                <tr
                  key={row.key}
                  data-testid={`log-detalle-diff-row-${row.key}`}
                  className={row.changed ? 'border-t bg-warning/10' : 'border-t'}
                >
                  <td className="px-3 py-2 font-mono text-xs">{row.key}</td>
                  <td className="whitespace-pre-wrap break-all px-3 py-2 text-xs">
                    {stringifyAuditValue(row.before)}
                  </td>
                  <td className="whitespace-pre-wrap break-all px-3 py-2 text-xs">
                    {stringifyAuditValue(row.after)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
