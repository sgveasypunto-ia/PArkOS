/**
 * `<Cupos />` — admin screen for cupo (cantidad-vehiculos-sucursal) CRUD
 * (PR-D.4, PR2 of the web_admin redesign).
 *
 * Same shape as `<Tarifas />` with one extra typed error class:
 * ``CantidadBajoIngresosError`` (422 ``capacidad_insuficiente``, BR2
 * HU-F14.4) surfaces an actionable message with ``tipo`` and
 * ``ocupadoActual`` / ``solicitado``.
 *
 * The list is filtered strictly by the branch selected in the topbar
 * selector. Cross-branch views are out of scope for this screen —
 * the multi-branch admin view lives in a separate dashboard surface.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  VersionHistoryPanel,
  type VersionHistoryItem,
} from '@/features/configuracion/components/VersionHistoryPanel';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import { createTipoVehiculo } from '@/features/tipos-vehiculo/api/tiposVehiculoApi';
import { useTiposVehiculo } from '@/features/tipos-vehiculo/hooks/useTiposVehiculo';
import { useSucursal } from '@/lib/sucursal-context';

import {
  CantidadBajoIngresosError,
  CantidadOverlapError,
  CantidadSucursalInmutableError,
  createCupo,
  updateCupo,
  type Cupo,
  type CupoCreateInput,
} from '../api/cuposApi';
import { useCantidadByKey } from '../hooks/useCantidadByKey';
import { useCantidadList } from '../hooks/useCantidadList';
import { CupoFormHarness } from '../components/CupoForm';

type ErrorState =
  | { kind: 'overlap' | 'inmutable' | 'bajo_ingresos' | 'network'; message: string }
  | null;

function mapError(err: unknown): ErrorState {
  if (err instanceof CantidadOverlapError) {
    return {
      kind: 'overlap',
      message: `La nueva ventana se solapa con el cupo ${err.conflictingUuid} (vigente desde ${err.conflictingVigenteDesde ?? '?'}). Elegí otro instante o actualizá el existente.`,
    };
  }
  if (err instanceof CantidadBajoIngresosError) {
    return {
      kind: 'bajo_ingresos',
      message: `Hay ${err.ocupadoActual} vehiculo(s) ocupando el tipo ${err.tipo ?? '?'}; no podés bajar el cupo a ${err.solicitado}. Cerrá o anulá los ingresos primero.`,
    };
  }
  if (err instanceof CantidadSucursalInmutableError) {
    return {
      kind: 'inmutable',
      message: `El cupo pertenece a la sucursal ${err.existingSucursal}; no se puede cambiar a ${err.attemptedSucursal}.`,
    };
  }
  const message = err instanceof Error ? err.message : 'Error desconocido';
  return { kind: 'network', message };
}

function toHistoryItem(c: Cupo): VersionHistoryItem {
  return {
    uuid: c.uuid,
    display: String(c.cantidad ?? '—'),
    vigente_desde: c.vigente_desde,
    vigente_hasta: c.vigente_hasta,
    estado: c.estado,
  };
}

interface ListContentProps {
  cupos: Cupo[];
  sucursales: Array<{ uuid: string; nombre: string | null }> | undefined;
  tiposVehiculo: Array<{ uuid: string; tipo: string | null }>;
  onEdit: (c: Cupo) => void;
  onToggleHistory: (sucursal: string, tipoVehiculo: string | null) => void;
  historyOpenFor: { sucursal: string; tipoVehiculo: string | null } | null;
  historyVersiones: Cupo[];
  emptyMessage: string;
}

function ListContent({
  cupos,
  sucursales,
  tiposVehiculo,
  onEdit,
  onToggleHistory,
  historyOpenFor,
  historyVersiones,
  emptyMessage,
}: ListContentProps): JSX.Element {
  const { t } = useTranslation();

  if (cupos.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
        data-testid="cupo-empty"
      >
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {cupos.map((cupo) => {
        const sucursalKey = cupo.uuid_sucursal ?? 'sin-sucursal';
        const sucursalNombre =
          sucursales?.find((s) => s.uuid === sucursalKey)?.nombre ??
          t('cupos.withoutSucursal', 'Sin sucursal');
        const tipoVehiculoNombre =
          cupo.uuid_tipo_vehiculo
            ? (tiposVehiculo.find((tv) => tv.uuid === cupo.uuid_tipo_vehiculo)?.tipo ??
              t('cupos.unknownTipo', 'Desconocido'))
            : t('cupos.anyTipo', 'Cualquiera');
        const tipoVehiculoKey = cupo.uuid_tipo_vehiculo ?? null;
        const isHistoryOpen =
          historyOpenFor !== null &&
          historyOpenFor.sucursal === sucursalKey &&
          historyOpenFor.tipoVehiculo === tipoVehiculoKey;
        return (
          <Card
            key={cupo.uuid}
            data-testid={`cupo-sucursal-group-${sucursalKey}`}
          >
            <CardHeader>
              <CardTitle>{sucursalNombre}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-3 py-2 text-left">
                      {t('cupos.col.tipoVehiculo', 'Tipo de vehículo')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('cupos.col.cantidad', 'Cantidad')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('cupos.col.acciones', 'Acciones')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    key={cupo.uuid}
                    data-testid={`cupo-row-${cupo.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td
                      className="px-3 py-2"
                      data-testid={`cupo-tipo-${cupo.uuid}`}
                    >
                      {tipoVehiculoNombre}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {cupo.cantidad ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => onEdit(cupo)}
                          data-testid={`cupo-edit-${cupo.uuid}`}
                        >
                          {t('cupos.action.edit', 'Editar')}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onToggleHistory(sucursalKey, tipoVehiculoKey)}
                          data-testid={`cupo-history-${cupo.uuid}`}
                        >
                          {isHistoryOpen
                            ? t('cupos.action.hideHistory', 'Ocultar histórico')
                            : t('cupos.action.history', 'Ver histórico')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              {isHistoryOpen && (
                <div className="border-t p-4">
                  <VersionHistoryPanel
                    versions={historyVersiones.map(toHistoryItem)}
                    displayLabel={t('cupos.historyLabel', 'Cantidad')}
                    defaultExpanded
                    contentProps={{
                      'data-testid': `cupo-history-${sucursalKey}`,
                    }}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

export default function Cupos(): JSX.Element {
  const { t } = useTranslation();
  const { selected: selectedSucursal } = useSucursal();

  const { sucursales } = useSucursalesDirectorio();

  const { cupos, refresh, isLoading, error } = useCantidadList();
  const { tipos: tiposVehiculo, refresh: refreshTipos } = useTiposVehiculo();
  const [editing, setEditing] = useState<Cupo | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isCreatingTipo, setIsCreatingTipo] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<
    { sucursal: string; tipoVehiculo: string | null } | null
  >(null);

  const activeFiltered = useMemo(() => {
    if (!selectedSucursal) return cupos;
    return cupos.filter((c) => c.uuid_sucursal === selectedSucursal);
  }, [cupos, selectedSucursal]);

  // Set of ``uuid_tipo_vehiculo`` already in use by an OPEN cupo
  // (``vigente_hasta IS NULL``) for the selected branch. Used by
  // ``<CupoForm>`` to filter the tipo select on CREATE (each
  // ``(sucursal, uuid_tipo_vehiculo)`` cell can hold at most one open
  // cupo; the backend's overlap guard already enforces this with 409,
  // we just hide the conflict from the UI). Sentinel ``'__NULL__'``
  // stands in for ``uuid_tipo_vehiculo === null`` (the "Cualquiera"
  // cell — bi-temporal NULL semantics mean it is its own distinct
  // cell, not a synonym for "no filter").
  const tiposEnUsoEnSucursal = useMemo(() => {
    const used = new Set<string>();
    for (const c of activeFiltered) {
      used.add(c.uuid_tipo_vehiculo ?? '__NULL__');
    }
    return used;
  }, [activeFiltered]);

  // Ver histórico: pass the specific (sucursal, tipo_vehiculo) business
  // key the "Ver histórico" button was clicked for -- omitting
  // tipo_vehiculo (as this used to) means "match rows where
  // uuid_tipo_vehiculo IS NULL" (`is_not_distinct_from`, same NULL-is-a
  // -valid-business-value semantics as the "Cualquiera" cell), not "any
  // tipo", so every real cupo's history always came back empty.
  const historySucursal =
    historyOpenFor === null || historyOpenFor.sucursal === 'sin-sucursal'
      ? null
      : historyOpenFor.sucursal;
  const { versiones: historyVersiones } = useCantidadByKey(
    historySucursal,
    historyOpenFor?.tipoVehiculo ?? null,
  );

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  async function onSubmit(values: CupoCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      const payload = { ...values, uuid_sucursal: selectedSucursal ?? null };
      if (editing !== null) {
        await updateCupo(editing.uuid, payload);
      } else {
        await createCupo(payload);
      }
      closeModal();
      await refresh();
    } catch (err) {
      setErrorState(mapError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function onTipoCreated(nombre: string): Promise<{ uuid: string }> {
    setIsCreatingTipo(true);
    try {
      const created = await createTipoVehiculo({ tipo: nombre });
      await refreshTipos();
      return { uuid: created.uuid };
    } finally {
      setIsCreatingTipo(false);
    }
  }

  function handleEdit(c: Cupo): void {
    setEditing(c);
    setCreating(false);
    setErrorState(null);
  }

  function handleToggleHistory(sucursal: string, tipoVehiculo: string | null): void {
    setHistoryOpenFor((current) =>
      current !== null &&
      current.sucursal === sucursal &&
      current.tipoVehiculo === tipoVehiculo
        ? null
        : { sucursal, tipoVehiculo },
    );
  }

  const activeSucursalLabel =
    sucursales?.find((s) => s.uuid === selectedSucursal)?.nombre ?? selectedSucursal ?? '';

  return (
    <div
      className="flex flex-1 flex-col gap-6 bg-background p-4 md:p-6 lg:p-8"
      data-testid="page-cupos"
    >
      <PageHeader
        title={t('cupos.title', 'Cupos')}
        actions={
          <Button
            type="button"
            onClick={() => {
              setCreating(true);
              setEditing(null);
              setErrorState(null);
            }}
            data-testid="cupo-new"
          >
            {t('cupos.new', 'Nuevo cupo')}
          </Button>
        }
      />

      {(creating || editing !== null) && (
        <FormModal
          open={true}
          onOpenChange={(open) => {
            if (!open) closeModal();
          }}
          title={
            editing !== null
              ? t('cupos.editTitle', 'Editar cupo')
              : t('cupos.createTitle', 'Nuevo cupo')
          }
          description={t(
            'cupos.modalDescription',
            'Cargá los datos. El cupo pertenece a la sucursal elegida y entra en vigencia al instante seleccionado.',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'cupo-form-modal' }}
        >
          {editing !== null ? (
            <CupoFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialCupo={editing}
              onCancel={closeModal}
              sucursalNombre={activeSucursalLabel}
              tiposVehiculo={tiposVehiculo}
              tiposEnUsoEnSucursal={tiposEnUsoEnSucursal}
              onTipoCreated={onTipoCreated}
              isCreatingTipo={isCreatingTipo}
            />
          ) : (
            <CupoFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialCupo={null}
              onCancel={closeModal}
              sucursalNombre={activeSucursalLabel}
              tiposVehiculo={tiposVehiculo}
              tiposEnUsoEnSucursal={tiposEnUsoEnSucursal}
              onTipoCreated={onTipoCreated}
              isCreatingTipo={isCreatingTipo}
            />
          )}
        </FormModal>
      )}

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('cupos.loadError', 'No se pudieron cargar los cupos.')}
        </p>
      )}

      {isLoading && cupos.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('cupos.loading', 'Cargando cupos...')}
        </p>
      )}

      {!selectedSucursal ? (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="cupos-active-empty-selection"
        >
          {t(
            'cupos.tabs.activeEmpty',
            'Elegí una sucursal en el selector del topbar para ver sus cupos.',
          )}
        </p>
      ) : (
        <ListContent
          cupos={activeFiltered}
          sucursales={sucursales}
          tiposVehiculo={tiposVehiculo}
          onEdit={handleEdit}
          onToggleHistory={handleToggleHistory}
          historyOpenFor={historyOpenFor}
          historyVersiones={historyVersiones}
          emptyMessage={t(
            'cupos.tabs.activeEmptyForBranch',
            'Esta sucursal no tiene cupos configurados.',
          )}
        />
      )}
    </div>
  );
}
