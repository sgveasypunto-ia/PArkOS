/**
 * `<ClienteBitacoraTab />` — tab "Bitácora" de `ClienteDetalle`
 * (HU-F20.1). Mirrors `features/parametrizacion/components/
 * SucursalBitacoraTab.tsx`'s pattern (SWR + `fetchAuditLog`,
 * `<HashChainStatus>`, same loading/error/empty states).
 *
 * **Contract verification done before wiring this (per task brief) —
 * per-cliente filtering is NOT feasible today**:
 *
 *   - `auditSchema.ts`'s `AuditQuery` / the backend's
 *     `AuditLogQueryParams` (`schemas/log_transaccional.py`) accept
 *     ONLY `uuid_sucursal`, `tabla_afectada`, `limit`, `cursor`. There is
 *     no per-affected-record filter query param.
 *   - `AuditLogItem` (the response row) DOES carry a field named
 *     `uuid_referencia` -- but that is a DIFFERENT column from the one
 *     `repo/versioned.py::close_and_insert` actually stamps with the
 *     audited row's own uuid on every generic `make_router` write
 *     (`log_attrs["uuid_registro_afectado"] = new_row.uuid`, see that
 *     module). `uuid_registro_afectado` is the column that would let the
 *     frontend match a log row back to a specific cliente, and it is
 *     simply never serialized by `AuditLogItem` (compare its field list
 *     against `models/A/log_transaccional.py`, which declares BOTH
 *     `uuid_registro_afectado` and `uuid_referencia` as distinct nullable
 *     columns). `uuid_referencia` stays `null` for every `clientes` write
 *     through this path.
 *
 * Net result: this tab falls back to the task brief's option (a)/(b) --
 * it reads `tabla_afectada=clientes` UNFILTERED (every cliente's audit
 * rows, paginated, newest first) rather than nothing. Per-cliente
 * filtering needs a backend addition (exposing `uuid_registro_afectado`
 * on `AuditLogItem` and/or a query filter) that is explicitly out of
 * scope here (audit endpoints are not modified by this change) --
 * flagged in the HU-F20.1 report.
 */
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';
import { ShieldAlert, ShieldCheck } from 'lucide-react';

import { HashChainStatus } from '@/components/HashChainStatus';
import { fetchAuditLog } from '@/features/audit/api/auditApi';

type ClienteBitacoraRow = {
  uuid: string;
  timestamp_evento: string;
  uuid_usuario: string | null;
  accion: string | null;
  hash_anterior: string | null;
  hash_actual: string | null;
};

export interface ClienteBitacoraTabProps {
  uuidCliente: string;
}

export function ClienteBitacoraTab({ uuidCliente }: ClienteBitacoraTabProps): JSX.Element {
  const { t } = useTranslation();
  // `uuidCliente` keeps the SWR key distinct per route (and documents
  // intent for a future per-cliente filter) -- it is NOT sent to the
  // backend as a filter; see the module docblock above for why.
  const swrKey = `/admin/audit/log?tabla_afectada=clientes&cliente=${uuidCliente}`;
  const { data, error, isLoading } = useSWR<{
    items: ClienteBitacoraRow[];
    next_cursor: string | null;
  }>(
    swrKey,
    async () => fetchAuditLog({ tabla_afectada: 'clientes', limit: 20 }),
    { revalidateOnFocus: false },
  );

  return (
    <section
      aria-label="Bitácora de cambios de clientes"
      className="space-y-4"
      data-testid="cliente-bitacora-root"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">
            {t('clienteBitacora.title', 'Bitácora de cambios')}
          </h3>
          <p className="text-muted-foreground text-xs">
            {t(
              'clienteBitacora.subtitle',
              'Cambios recientes sobre clientes (no filtrado a este cliente puntual -- ver nota técnica). Máx. 20 filas.',
            )}
          </p>
        </div>
      </header>

      {isLoading && (
        <p
          role="status"
          className="text-muted-foreground text-sm"
          data-testid="cliente-bitacora-loading"
        >
          {t('common.loading', 'Cargando…')}
        </p>
      )}

      {error && !isLoading && (
        <div
          role="alert"
          data-testid="cliente-bitacora-error"
          className="flex items-start gap-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t(
              'clienteBitacora.errorLoading',
              'No se pudo cargar la bitácora. Reintenta en un momento.',
            )}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) === 0 && (
        <div
          role="status"
          data-testid="cliente-bitacora-empty"
          className="flex items-start gap-3 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm text-muted-foreground"
        >
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            {t('clienteBitacora.empty', 'Sin cambios registrados aún para clientes.')}
          </span>
        </div>
      )}

      {!isLoading && !error && (data?.items.length ?? 0) > 0 && (
        <ol
          data-testid="cliente-bitacora-list"
          className="space-y-3"
          aria-label="Eventos de la bitácora"
        >
          {data!.items.map((row) => (
            <li
              key={row.uuid}
              data-testid={`cliente-bitacora-row-${row.uuid}`}
              className="rounded-lg border bg-card px-4 py-3 text-sm"
            >
              <header className="flex items-center justify-between gap-2">
                <div className="flex flex-col">
                  <span className="font-medium" data-testid="cliente-bitacora-accion">
                    {row.accion ?? '—'}
                  </span>
                  <time
                    dateTime={row.timestamp_evento}
                    className="text-muted-foreground text-xs"
                    data-testid="cliente-bitacora-timestamp"
                  >
                    {row.timestamp_evento}
                  </time>
                </div>
                <HashChainStatus hashAnterior={row.hash_anterior} hashActual={row.hash_actual} />
              </header>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
