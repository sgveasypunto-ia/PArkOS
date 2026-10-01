/**
 * `EmpresaBitacoraTab` — tab "Bitácora" del singleton Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 * El endpoint canónico de auditoría (`GET /api/v1/admin/audit/log`)
 * requiere `uuid_sucursal` para el dashboard por-branch. Empresa es
 * un singleton tenant-global sin `uuid_sucursal`, así que el caso
 * cross-tab se cableó en el BE con un filtro alternativo
 * `tabla_afectada` (H15.2 wire-up 2026-10-01): el handler acepta
 * `tabla_afectada='empresa'` como selector alternativo cuando no hay
 * sucursal. Ver `schemas/log_transaccional.py::AuditLogQueryParams`
 * + `api/v1/audit.py::list_audit_log`.
 *
 * El tab renderiza cada fila con su cadena hash (anterior -> actual)
 * reutilizando `HashChainStatus`, igual que el AuditDashboard general
 * (IT-12). Los campos `datos_anteriores`/`datos_nuevos` se muestran
 * como un par "antes/después" en JSON preformateado — Empresa es
 * un singleton así que se esperan muy pocas filas (decenas a lo mucho,
 * no las 100K+ del AuditDashboard general).
 *
 * Empty state: cuando no hay filas, una sola línea "Sin cambios
 * registrados aún" con data-testid `empresa-bitacora-empty` (el
 * T4 del EmpresaPage.test.tsx verifica el render del tab; este testid
 * es distinto al placeholder original que tenía T4).
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { ShieldAlert, ShieldCheck } from 'lucide-react';

import { HashChainStatus } from '@/components/HashChainStatus';
import { fetchAuditLog } from '@/features/audit/api/auditApi';

type EmpresaBitacoraRow = {
  uuid: string;
  timestamp_evento: string;
  uuid_usuario: string | null;
  accion: string | null;
  hash_anterior: string | null;
  hash_actual: string | null;
  datos_anteriores: Record<string, unknown> | null;
  datos_nuevos: Record<string, unknown> | null;
};

function renderJson(value: Record<string, unknown> | null): string {
  if (value === null) return '—';
  return JSON.stringify(value, null, 2);
}

export interface EmpresaBitacoraTabProps {
  /**
   * Optional suffix for the SWR cache key. Tests use this to keep
   * cache entries separate between cases (the default global provider
   * persists between tests in the same vitest worker).
   */
  swrKeySuffix?: string;
}

export function EmpresaBitacoraTab({ swrKeySuffix }: EmpresaBitacoraTabProps = {}): JSX.Element {
  const { t } = useTranslation();
  // HU-F15.2: Empresa es un singleton; el filtro `tabla_afectada='empresa'`
  // resuelve cada fila de ``prod.log_transaccional`` cuyo
  // ``tabla_afectada`` coincide (sin restricción por sucursal). El SWR
  // key se construye a partir del filtro para que un cambio entre tabs
  // revalide cuando el usuario navegue de vuelta.
  const swrKey =
    '/admin/audit/log?tabla_afectada=empresa&limit=20' +
    (swrKeySuffix !== undefined ? `&_=${swrKeySuffix}` : '');
  const { data, error, isLoading } = useSWR<{ items: EmpresaBitacoraRow[]; next_cursor: string | null }>(
    swrKey,
    async () => fetchAuditLog({ tabla_afectada: 'empresa', limit: 20 }),
    { revalidateOnFocus: false },
  );

  return (
    <section
      aria-label="Bitácora de cambios de Empresa"
      className="space-y-4"
      data-testid="empresa-bitacora-root"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">
            {t('empresa.bitacora.title', 'Bitácora de cambios')}
          </h3>
          <p className="text-muted-foreground text-xs">
            {t(
              'empresa.bitacora.subtitle',
              'Cada modificación del singleton Empresa con su cadena hash. Máx. 20 filas.',
            )}
          </p>
        </div>
      </header>

      {isLoading && (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="empresa-bitacora-loading"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          data-testid="empresa-bitacora-error"
          className="flex items-start gap-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t(
              'empresa.bitacora.errorLoading',
              'No se pudo cargar la bitácora. Reintenta en un momento.',
            )}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) === 0 && (
        <div
          role="status"
          data-testid="empresa-bitacora-empty"
          className="flex items-start gap-3 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t(
              'empresa.bitacora.empty',
              'Sin cambios registrados aún. La bitácora se pobla automáticamente con cada edición.',
            )}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) > 0 && (
        <ol
          data-testid="empresa-bitacora-list"
          className="space-y-3"
          aria-label="Eventos de la bitácora"
        >
          {data!.items.map((row) => (
            <li
              key={row.uuid}
              data-testid={`empresa-bitacora-row-${row.uuid}`}
              className="rounded-lg border bg-card px-4 py-3 text-sm"
            >
              <header className="mb-2 flex items-center justify-between gap-2">
                <div className="flex flex-col">
                  <span
                    className="font-medium"
                    data-testid="empresa-bitacora-accion"
                  >
                    {row.accion ?? '—'}
                  </span>
                  <time
                    dateTime={row.timestamp_evento}
                    className="text-muted-foreground text-xs"
                    data-testid="empresa-bitacora-timestamp"
                  >
                    {row.timestamp_evento}
                  </time>
                </div>
                <HashChainStatus
                  hashAnterior={row.hash_anterior}
                  hashActual={row.hash_actual}
                />
              </header>
              {(row.datos_anteriores !== null || row.datos_nuevos !== null) && (
                <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div>
                    <p className="text-muted-foreground text-xs">antes</p>
                    <pre
                      data-testid="empresa-bitacora-antes"
                      className="overflow-x-auto rounded-md border bg-muted/30 p-2 font-mono text-xs"
                    >
                      {renderJson(row.datos_anteriores)}
                    </pre>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">después</p>
                    <pre
                      data-testid="empresa-bitacora-despues"
                      className="overflow-x-auto rounded-md border bg-muted/30 p-2 font-mono text-xs"
                    >
                      {renderJson(row.datos_nuevos)}
                    </pre>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}