/**
 * `<LogTable />` -- presentational table for the IT-12 audit log.
 *
 * Renders a compact per-row badge with:
 *   - timestamp_evento (formatted es-CO short)
 *   - accion (e.g. "test_create", "crear_factura")
 *   - tabla_afectada (e.g. "ingreso")
 *   - hash-chain link (hash_anterior -> hash_actual, abbreviated to
 *     8 chars each so the row stays scannable)
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 *   - <table> with <caption> + <th scope="col"> so screen readers
 *     announce column headers per cell.
 *   - Empty branch state rendered as a single row with
 *     colspan={N} + role="status" aria-live="polite".
 *   - Error state has role="alert" aria-live="assertive".
 */
import { useTranslation } from 'react-i18next';

import type { AuditLogItem } from '../api/auditSchema';

export interface LogTableProps {
  items: AuditLogItem[];
  isLoading: boolean;
  error: Error | null | undefined;
}

function abbreviateHash(hash: string | null): string {
  if (hash === null) return '—';
  // First 8 hex chars are enough to spot a chain break in a list view;
  // the full 64-char hash is exposed in the row's title attribute.
  return `${hash.slice(0, 8)}…`;
}

function formatTimestamp(iso: string): string {
  // The backend stamps naive UTC; we display es-CO short. The browser
  // timezone is irrelevant -- we format in UTC explicitly.
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace('T', ' ').slice(0, 19);
}

export function LogTable({ items, isLoading, error }: LogTableProps) {
  const { t } = useTranslation();

  if (error !== null && error !== undefined) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="audit-log-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (isLoading && items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="audit-log-loading"
        className="text-sm text-muted-foreground"
      >
        {t('audit.loading')}
      </p>
    );
  }

  if (items.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="audit-log-empty"
        className="text-sm text-muted-foreground"
      >
        {t('audit.empty')}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-card">
      <table className="w-full text-sm" data-testid="audit-log-table">
        <caption className="sr-only">{t('audit.tableCaption')}</caption>
        <thead>
          <tr className="border-b text-left">
            <th scope="col" className="px-3 py-2">
              {t('audit.col.timestamp')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('audit.col.accion')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('audit.col.tabla')}
            </th>
            <th scope="col" className="px-3 py-2">
              {t('audit.col.hashChain')}
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.uuid} className="border-b" data-testid="audit-row">
              <td className="px-3 py-2 font-mono text-xs" title={it.timestamp_evento}>
                {formatTimestamp(it.timestamp_evento)}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{it.accion ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-xs">{it.tabla_afectada ?? '—'}</td>
              <td className="px-3 py-2 font-mono text-xs">
                <span
                  title={`${it.hash_anterior ?? '?'} -> ${it.hash_actual ?? '?'}`}
                  className="inline-flex items-center gap-1"
                >
                  <span className="text-muted-foreground">{abbreviateHash(it.hash_anterior)}</span>
                  <span aria-hidden="true">&rarr;</span>
                  <span>{abbreviateHash(it.hash_actual)}</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
