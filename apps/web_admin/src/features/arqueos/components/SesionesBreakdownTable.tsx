/**
 * ``<SesionesBreakdownTable>`` -- per-session drill-down for a
 * ``cierre_dia`` aggregate (HU-F18.2 + Bug #2 fix, 2026-10-14).
 *
 * Renders the ``sesiones[]`` array returned by
 * ``GET /api/v1/caja/arqueo/resumen?uuid_sucursal=&fecha=`` so the
 * admin can see WHICH operator turns contributed to the day-level
 * aggregate. One row per sesion:
 *   - ``uuid_sesion`` (truncated to 8 chars for readability)
 *   - operator (``uuid_usuario`` truncated)
 *   - ``timestamp_apertura`` (ISO; sortable in BE)
 *   - ``timestamp_cierre`` (null = still open; the panel shows "—")
 *   - ``valor_efectivo_esperado`` (the operator's base + cobros in
 *     efectivo during the turn; the per-session difference is not
 *     exposed by the wire and is computed server-side on the day-level
 *     aggregate only)
 *
 * The component is purely presentational. Loading + error are
 * rendered inline per section. An empty state appears when the BE
 * returned no sesiones (e.g. the day is still empty).
 */
import { useTranslation } from 'react-i18next';

import type { ArqueoResumenItem } from '../api/arqueosSchema';

export interface SesionesBreakdownTableProps {
  sesiones: ArqueoResumenItem[];
  isLoading: boolean;
  error: Error | undefined;
  onRetry: () => void;
}

function formatMoney(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const num = Number(value);
  if (Number.isNaN(num)) return value;
  return num.toLocaleString('es-CO', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });
}

function formatTimestamp(ts: string | null | undefined): string {
  if (ts === null || ts === undefined) return '—';
  return ts.slice(0, 19).replace('T', ' ');
}

export function SesionesBreakdownTable({
  sesiones,
  isLoading,
  error,
  onRetry,
}: SesionesBreakdownTableProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <h2 className="text-base font-semibold">
        {t('arqueos.detail.sesionesTitle', 'Sesiones que aportaron al cierre')}
      </h2>
      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="sesiones-breakdown-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t(
            'arqueos.detail.errorLoading',
            'No se pudo cargar esta sección.',
          )}{' '}
          <button
            type="button"
            className="underline"
            onClick={onRetry}
          >
            {t('arqueos.detail.retry', 'Reintentar')}
          </button>
        </p>
      ) : isLoading && sesiones.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="sesiones-breakdown-loading"
          className="text-sm text-muted-foreground"
        >
          {t('arqueos.detail.loading', 'Cargando…')}
        </p>
      ) : sesiones.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="sesiones-breakdown-empty"
          className="rounded-md border border-dashed bg-muted/30 px-3 py-4 text-center text-sm text-muted-foreground"
        >
          {t(
            'arqueos.detail.noSesiones',
            'No hay sesiones registradas en el día.',
          )}
        </p>
      ) : (
        <table
          data-testid="sesiones-breakdown-table"
          className="w-full text-sm"
        >
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="px-3 py-2 font-medium">
                {t('arqueos.detail.sesion', 'Sesión')}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {t('arqueos.detail.operador', 'Operador')}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {t('arqueos.detail.apertura', 'Apertura')}
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                {t('arqueos.detail.cierre', 'Cierre')}
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-medium"
              >
                {t(
                  'arqueos.detail.efectivoEsperado',
                  'Efectivo esperado',
                )}
              </th>
            </tr>
          </thead>
          <tbody>
            {sesiones.map((row) => (
              <tr
                key={row.uuid_sesion ?? 'unknown'}
                data-testid={`sesion-row-${row.uuid_sesion ?? 'unknown'}`}
                className="border-t"
              >
                <td className="px-3 py-2 font-mono text-xs">
                  {row.uuid_sesion ? row.uuid_sesion.slice(0, 8) : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {row.uuid_usuario
                    ? row.uuid_usuario.slice(0, 8)
                    : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {formatTimestamp(row.timestamp_apertura)}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  {formatTimestamp(row.timestamp_cierre)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatMoney(row.valor_efectivo_esperado)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
