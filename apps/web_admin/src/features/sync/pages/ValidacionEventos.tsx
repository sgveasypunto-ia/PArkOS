/**
 * `<ValidacionEventos />` — HU-F19.6 "Validación de eventos" tab:
 * cursor-paginated `validacion_evento` inbox (CU-07), filterable by
 * sucursal + estado, with a per-row approve/reject action
 * (`<ValidarEventoModal />` -> `POST /api/v1/validacion-evento`).
 *
 * Mounted as a 4th tab inside `<SyncDashboard />` (see that file's
 * docblock for why `/sync` stays ONE route with a `<Tabs>` shell instead
 * of a standalone `/sync/validacion-eventos` route) — same convention
 * `SyncLog` / `SyncConflict` already established for this dashboard.
 *
 * Per-row history (design decision, not fully specified by the HU):
 * `list_validacion_evento` filters `WHERE vigente_hasta IS NULL`
 * server-side (`dian/cloud_router.py::_list_workflow_rows`), i.e. it
 * ONLY ever returns the CURRENT tip of each chain, and there is no
 * `GET /validacion-evento/{uuid}` endpoint to walk `uuid_validacion_padre`
 * backwards (unlike `alerta`, which has one and lets
 * `alertas/hooks/useAlertaChain.ts` do a real multi-hop walk). Each row's
 * "historial" therefore renders through the generic `<WorkflowChain />`
 * as a single-transition chain built from that row's own fields — reusing
 * the same visual language `AlertaDetalle` uses for its chain, not an
 * actual multi-hop walk (there is nothing further to walk, server-side,
 * for this table today).
 */
import { Fragment, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeProps } from '@/components/ui/badge';

import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import {
  WorkflowChain,
  type WorkflowTransition,
} from '@/features/workflows/components/WorkflowChain';

import { useValidacionEventos } from '../hooks/useValidacionEventos';
import { ValidarEventoModal } from '../components/ValidarEventoModal';
import {
  VALIDACION_EVENTO_ESTADOS,
  type ValidacionEventoEstado,
  type ValidacionEventoRead,
} from '../api/validacionEventoSchema';

export interface ValidacionEventosProps {
  /** Pre-fills the sucursal filter (mirrors SyncLog/SyncConflict's drill-down prop). */
  initialUuidSucursal?: string | null;
  /** Test-only hook to isolate the SWR cache across cases (mirrors useAlertasAdmin's swrSalt). */
  swrSalt?: string;
}

const ESTADO_BADGE: Record<
  ValidacionEventoEstado,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  pendiente: {
    labelKey: 'sync.validacionEventos.estado.pendiente',
    fallback: 'Pendiente',
    variant: 'warning',
  },
  validado: {
    labelKey: 'sync.validacionEventos.estado.validado',
    fallback: 'Validado',
    variant: 'success',
  },
  rechazado: {
    labelKey: 'sync.validacionEventos.estado.rechazado',
    fallback: 'Rechazado',
    variant: 'destructive',
  },
};

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().replace('T', ' ').slice(0, 19);
}

function toTransition(item: ValidacionEventoRead, fallbackLabel: string): WorkflowTransition {
  return {
    id: item.uuid,
    status: item.estado ?? fallbackLabel,
    timestamp: item.timestamp_evento ?? item.created_at,
    actor: item.uuid_usuario,
    observaciones: item.observaciones,
  };
}

export default function ValidacionEventos({
  initialUuidSucursal = null,
  swrSalt,
}: ValidacionEventosProps): JSX.Element {
  const { t } = useTranslation();
  const { sucursales } = useSucursalesDirectorio();

  const [uuidSucursal, setUuidSucursal] = useState<string>(initialUuidSucursal ?? '');
  const [estado, setEstado] = useState<ValidacionEventoEstado | ''>('');
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null);
  const [activeItem, setActiveItem] = useState<ValidacionEventoRead | null>(null);

  const query = useMemo(
    () => ({
      uuid_sucursal: uuidSucursal || undefined,
      estado: estado || undefined,
      limit: 50,
    }),
    [uuidSucursal, estado],
  );

  const { items, isLoading, error, hasMore, loadMore, refresh } = useValidacionEventos(query, {
    swrSalt,
  });

  function renderBadge(status: string): JSX.Element {
    if (status === 'pendiente' || status === 'validado' || status === 'rechazado') {
      const badge = ESTADO_BADGE[status];
      return (
        <Badge variant={badge.variant} data-testid={`validacion-eventos-badge-${status}`}>
          {t(badge.labelKey, badge.fallback)}
        </Badge>
      );
    }
    return (
      <Badge variant="outline" data-testid="validacion-eventos-badge-none">
        {t('sync.validacionEventos.estado.none', '—')}
      </Badge>
    );
  }

  return (
    <div className="flex flex-col gap-3" data-testid="validacion-eventos-tab">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('sync.validacionEventos.filterSucursal', 'Sucursal')}
          </span>
          <select
            className="w-56 rounded-md border bg-background px-2 py-1 text-sm"
            value={uuidSucursal}
            onChange={(e) => setUuidSucursal(e.target.value)}
            data-testid="validacion-eventos-filter-sucursal"
          >
            <option value="">{t('sync.validacionEventos.filterSucursalAll', 'Todas')}</option>
            {sucursales.map((s) => (
              <option key={s.uuid} value={s.uuid}>
                {s.nombre ?? s.uuid.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-muted-foreground">
            {t('sync.validacionEventos.filterEstado', 'Estado')}
          </span>
          <select
            className="w-56 rounded-md border bg-background px-2 py-1 text-sm"
            value={estado}
            onChange={(e) => setEstado(e.target.value as ValidacionEventoEstado | '')}
            data-testid="validacion-eventos-filter-estado"
          >
            <option value="">{t('sync.validacionEventos.filterEstadoAll', 'Todos')}</option>
            {VALIDACION_EVENTO_ESTADOS.map((value) => (
              <option key={value} value={value}>
                {t(ESTADO_BADGE[value].labelKey, ESTADO_BADGE[value].fallback)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <p
          role="alert"
          aria-live="assertive"
          data-testid="validacion-eventos-error"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {error.message}
        </p>
      ) : isLoading && items.length === 0 ? (
        <p
          role="status"
          aria-live="polite"
          data-testid="validacion-eventos-loading"
          className="text-sm text-muted-foreground"
        >
          {t('sync.validacionEventos.loading', 'Cargando...')}
        </p>
      ) : (
        <>
          <Table data-testid="validacion-eventos-table">
            <TableCaption className="sr-only">
              {t('sync.validacionEventos.caption', 'Eventos recibidos pendientes de validación')}
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">
                  {t('sync.validacionEventos.col.sucursal', 'Sucursal')}
                </TableHead>
                <TableHead scope="col">
                  {t('sync.validacionEventos.col.tabla', 'Tabla origen')}
                </TableHead>
                <TableHead scope="col">
                  {t('sync.validacionEventos.col.fecha', 'Fecha del evento')}
                </TableHead>
                <TableHead scope="col">
                  {t('sync.validacionEventos.col.estado', 'Estado')}
                </TableHead>
                <TableHead scope="col" className="text-right">
                  {t('sync.validacionEventos.col.acciones', 'Acciones')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    role="status"
                    aria-live="polite"
                    data-testid="validacion-eventos-empty"
                    className="text-center text-sm text-muted-foreground"
                  >
                    {t(
                      'sync.validacionEventos.empty',
                      'No hay eventos para el filtro seleccionado.',
                    )}
                  </TableCell>
                </TableRow>
              ) : (
                items.map((row) => {
                  const canResolve = row.estado === 'pendiente';
                  return (
                    <Fragment key={row.uuid}>
                      <TableRow data-testid={`validacion-eventos-row-${row.uuid}`}>
                        <TableCell className="font-mono text-xs">
                          {sucursales.find((s) => s.uuid === row.uuid_sucursal)?.nombre ??
                            row.uuid_sucursal?.slice(0, 8) ??
                            '—'}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {row.tabla_origen ?? '—'}
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {formatDate(row.timestamp_evento)}
                        </TableCell>
                        <TableCell>{renderBadge(row.estado ?? '')}</TableCell>
                        <TableCell className="space-x-2 text-right">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setExpandedUuid((cur) => (cur === row.uuid ? null : row.uuid))
                            }
                            data-testid={`validacion-eventos-ver-historial-${row.uuid}`}
                          >
                            {expandedUuid === row.uuid
                              ? t('sync.validacionEventos.hideHistory', 'Ocultar historial')
                              : t('sync.validacionEventos.viewHistory', 'Ver historial')}
                          </Button>
                          <Button
                            type="button"
                            variant="default"
                            size="sm"
                            disabled={!canResolve}
                            onClick={() => setActiveItem(row)}
                            data-testid={`validacion-eventos-resolver-${row.uuid}`}
                            title={
                              canResolve
                                ? undefined
                                : t(
                                    'sync.validacionEventos.yaResuelto',
                                    'Este evento ya fue validado o rechazado.',
                                  )
                            }
                          >
                            {t('sync.validacionEventos.resolver', 'Validar / Rechazar')}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {expandedUuid === row.uuid && (
                        <TableRow>
                          <TableCell colSpan={5}>
                            <WorkflowChain
                              transitions={[
                                toTransition(
                                  row,
                                  t('sync.validacionEventos.estado.none', '—'),
                                ),
                              ]}
                              renderStatusBadge={renderBadge}
                            />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })
              )}
            </TableBody>
          </Table>

          {hasMore && (
            <div className="flex justify-center">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  void loadMore();
                }}
                data-testid="validacion-eventos-load-more"
              >
                {t('sync.validacionEventos.loadMore', 'Cargar más')}
              </Button>
            </div>
          )}
        </>
      )}

      {activeItem && (
        <ValidarEventoModal
          uuidValidacionPadre={activeItem.uuid}
          open
          onClose={() => setActiveItem(null)}
          onResuelto={() => {
            setActiveItem(null);
            void refresh();
          }}
        />
      )}
    </div>
  );
}
