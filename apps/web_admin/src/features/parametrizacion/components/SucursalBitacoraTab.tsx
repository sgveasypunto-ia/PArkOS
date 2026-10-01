/**
 * `SucursalBitacoraTab` — tab "Bitácora" de `SucursalDetalle.tsx` (HU-F15.1).
 *
 * Mismo enfoque que `features/empresa/components/EmpresaBitacoraTab.tsx`
 * (mismo endpoint `GET /api/v1/admin/audit/log`, mismo
 * `HashChainStatus`, mismos estados loading/error/empty), pero scopeado
 * a UNA sucursal via el filtro `uuid_sucursal` que el endpoint YA
 * soporta de forma nativa (`features/audit/api/auditApi.ts`) -- a
 * diferencia de Empresa (singleton sin `uuid_sucursal`, de ahí el
 * `tabla_afectada='empresa'` alternativo que ESE tab necesita), así que
 * acá no hace falta ningún wire-up adicional de backend.
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { ShieldAlert, ShieldCheck } from 'lucide-react';

import { HashChainStatus } from '@/components/HashChainStatus';
import { fetchAuditLog } from '@/features/audit/api/auditApi';

type SucursalBitacoraRow = {
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

export interface SucursalBitacoraTabProps {
  uuidSucursal: string;
}

export function SucursalBitacoraTab({ uuidSucursal }: SucursalBitacoraTabProps): JSX.Element {
  const { t } = useTranslation();
  const swrKey = `/admin/audit/log?uuid_sucursal=${uuidSucursal}&limit=20`;
  const { data, error, isLoading } = useSWR<{
    items: SucursalBitacoraRow[];
    next_cursor: string | null;
  }>(
    swrKey,
    async () => fetchAuditLog({ uuid_sucursal: uuidSucursal, limit: 20 }),
    { revalidateOnFocus: false },
  );

  return (
    <section
      aria-label="Bitácora de cambios de la sucursal"
      className="space-y-4"
      data-testid="sucursal-bitacora-root"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">
            {t('sucursal.bitacora.title', 'Bitácora de cambios')}
          </h3>
          <p className="text-muted-foreground text-xs">
            {t(
              'sucursal.bitacora.subtitle',
              'Cada modificación de esta sucursal con su cadena hash. Máx. 20 filas.',
            )}
          </p>
        </div>
      </header>

      {isLoading && (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="sucursal-bitacora-loading"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          data-testid="sucursal-bitacora-error"
          className="flex items-start gap-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t(
              'sucursal.bitacora.errorLoading',
              'No se pudo cargar la bitácora. Reintenta en un momento.',
            )}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) === 0 && (
        <div
          role="status"
          data-testid="sucursal-bitacora-empty"
          className="flex items-start gap-3 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t(
              'sucursal.bitacora.empty',
              'Sin cambios registrados aún para esta sucursal.',
            )}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) > 0 && (
        <ol
          data-testid="sucursal-bitacora-list"
          className="space-y-3"
          aria-label="Eventos de la bitácora"
        >
          {data!.items.map((row) => (
            <li
              key={row.uuid}
              data-testid={`sucursal-bitacora-row-${row.uuid}`}
              className="rounded-lg border bg-card px-4 py-3 text-sm"
            >
              <header className="mb-2 flex items-center justify-between gap-2">
                <div className="flex flex-col">
                  <span className="font-medium" data-testid="sucursal-bitacora-accion">
                    {row.accion ?? '—'}
                  </span>
                  <time
                    dateTime={row.timestamp_evento}
                    className="text-muted-foreground text-xs"
                    data-testid="sucursal-bitacora-timestamp"
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
                      data-testid="sucursal-bitacora-antes"
                      className="overflow-x-auto rounded-md border bg-muted/30 p-2 font-mono text-xs"
                    >
                      {renderJson(row.datos_anteriores)}
                    </pre>
                  </div>
                  <div>
                    <p className="text-muted-foreground text-xs">después</p>
                    <pre
                      data-testid="sucursal-bitacora-despues"
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
