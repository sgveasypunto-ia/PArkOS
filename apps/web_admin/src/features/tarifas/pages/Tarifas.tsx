/**
 * `<Tarifas />` — admin screen for tarifa CRUD (PR-D.3, PR2 of the
 * web_admin redesign).
 *
 * Layout:
 *   - Header: title + "Nueva tarifa" button.
 *   - TarifaForm modal (create + edit). Cancel dispatches close.
 *   - Single filtered list scoped to the branch selected in the topbar
 *     (`useSucursal().selected`). Cross-branch views are out of scope
 *     for this screen — the multi-branch admin view lives in a
 *     separate dashboard surface. Each row has an "Editar" button
 *     (PUT) and a "Ver histórico" toggle that reveals the
 *     VersionHistoryPanel below the list.
 *
 * Container/presentational split: this file owns state, SWR mutations,
 * and error mapping. TarifaForm and VersionHistoryPanel are presentational.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  VersionHistoryPanel,
  type VersionHistoryItem,
} from '@/features/configuracion/components/VersionHistoryPanel';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import { useTiposVehiculo } from '@/features/tipos-vehiculo/hooks/useTiposVehiculo';
import { useTipoTarifa } from '@/features/tipo-tarifa/hooks/useTipoTarifa';
import { useSucursal } from '@/lib/sucursal-context';

import {
  createTarifa,
  updateTarifa,
  TarifaOverlapError,
  TarifaSucursalInmutableError,
  type Tarifa,
  type TarifaCreateInput,
} from '../api/tarifasApi';
import { useTarifasByKey } from '../hooks/useTarifasByKey';
import { useTarifasList } from '../hooks/useTarifasList';
import { TarifaFormHarness } from '../components/TarifaForm';

type ErrorState = { kind: 'overlap' | 'inmutable' | 'network'; message: string } | null;

function mapError(err: unknown): ErrorState {
  if (err instanceof TarifaOverlapError) {
    return {
      kind: 'overlap',
      message: `La nueva ventana se solapa con la tarifa ${err.conflictingUuid} (vigente desde ${err.conflictingVigenteDesde ?? '?'}). Elegí otro instante o actualizá la existente.`,
    };
  }
  if (err instanceof TarifaSucursalInmutableError) {
    return {
      kind: 'inmutable',
      message: `La tarifa pertenece a la sucursal ${err.existingSucursal}; no se puede cambiar a ${err.attemptedSucursal}.`,
    };
  }
  const message = err instanceof Error ? err.message : 'Error desconocido';
  return { kind: 'network', message };
}

function toHistoryItem(t: Tarifa): VersionHistoryItem {
  return {
    uuid: t.uuid,
    display: t.valor ?? '—',
    vigente_desde: t.vigente_desde,
    vigente_hasta: t.vigente_hasta,
    estado: t.estado,
  };
}

interface ListContentProps {
  tarifas: Tarifa[];
  sucursales: Array<{ uuid: string; nombre: string | null }> | undefined;
  tiposVehiculo: Array<{ uuid: string; tipo: string | null }>;
  tiposTarifa: Array<{ uuid: string; tipo: string | null }>;
  onEdit: (t: Tarifa) => void;
  onToggleHistory: (sucursalKey: string) => void;
  historyOpenFor: string | null;
  historyVersiones: Tarifa[];
  emptyMessage: string;
}

function ListContent({
  tarifas,
  sucursales,
  tiposVehiculo,
  tiposTarifa,
  onEdit,
  onToggleHistory,
  historyOpenFor,
  historyVersiones,
  emptyMessage,
}: ListContentProps): JSX.Element {
  const { t } = useTranslation();

  if (tarifas.length === 0) {
    return (
      <p
        role="status"
        aria-live="polite"
        className="text-sm text-muted-foreground"
        data-testid="tarifa-empty"
      >
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {tarifas.map((tarifa) => {
        const sucursalKey = tarifa.uuid_sucursal ?? 'sin-sucursal';
        const sucursalNombre =
          sucursales?.find((s) => s.uuid === sucursalKey)?.nombre ??
          t('tarifas.withoutSucursal', 'Sin sucursal');
        const tipoVehiculoNombre = tarifa.uuid_tipo_vehiculo
          ? (tiposVehiculo.find((tv) => tv.uuid === tarifa.uuid_tipo_vehiculo)?.tipo ??
            t('tarifas.unknownTipoVehiculo', 'Desconocido'))
          : t('tarifas.tipoVehiculoAny', 'Cualquiera');
        const modalidadNombre = tarifa.uuid_tipo_tarifa
          ? (tiposTarifa.find((tt) => tt.uuid === tarifa.uuid_tipo_tarifa)?.tipo ??
            t('tarifas.unknownTipoTarifa', 'Desconocida'))
          : t('tarifas.tipoTarifaAny', 'Cualquiera');
        return (
          <Card
            key={tarifa.uuid}
            data-testid={`tarifa-sucursal-group-${sucursalKey}`}
          >
            <CardHeader>
              <CardTitle>{sucursalNombre}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-3 py-2">
                      {t('tarifas.col.tipoVehiculo', 'Tipo vehículo')}
                    </th>
                    <th className="px-3 py-2">
                      {t('tarifas.col.modalidad', 'Modalidad')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.valor', 'Valor')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.plena', 'Plena')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.acciones', 'Acciones')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    key={tarifa.uuid}
                    data-testid={`tarifa-row-${tarifa.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td
                      className="px-3 py-2 text-xs"
                      data-testid={`tarifa-tipo-${tarifa.uuid}`}
                    >
                      {tipoVehiculoNombre}
                    </td>
                    <td
                      className="px-3 py-2 text-xs"
                      data-testid={`tarifa-modalidad-${tarifa.uuid}`}
                    >
                      {modalidadNombre}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {tarifa.valor ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {tarifa.valor_plena ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => onEdit(tarifa)}
                          data-testid={`tarifa-edit-${tarifa.uuid}`}
                        >
                          {t('tarifas.action.edit', 'Editar')}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onToggleHistory(sucursalKey)}
                          data-testid={`tarifa-history-${tarifa.uuid}`}
                        >
                          {historyOpenFor === sucursalKey
                            ? t('tarifas.action.hideHistory', 'Ocultar histórico')
                            : t('tarifas.action.history', 'Ver histórico')}
                        </Button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              {historyOpenFor === sucursalKey && (
                <div className="border-t p-4">
                  <VersionHistoryPanel
                    versions={historyVersiones.map(toHistoryItem)}
                    displayLabel={t('tarifas.historyLabel', 'Valor')}
                    defaultExpanded
                    contentProps={{
                      'data-testid': `tarifa-history-${sucursalKey}`,
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

export default function Tarifas(): JSX.Element {
  const { t } = useTranslation();
  const { selected: selectedSucursal } = useSucursal();

  const { sucursales } = useSucursalesDirectorio();

  const { tarifas, refresh, isLoading, error } = useTarifasList(null);
  const { tipos: tiposVehiculo } = useTiposVehiculo();
  const { tipos: tiposTarifa } = useTipoTarifa();
  const [editing, setEditing] = useState<Tarifa | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<string | null>(null);

  const allFiltered = useMemo(() => {
    // Strict per-branch filter: the page is single-tenant by design.
    // Each tarifa belongs to one branch — the multi-branch admin view
    // lives in a separate dashboard surface.
    if (!selectedSucursal) return [];
    return tarifas.filter((tt) => tt.uuid_sucursal === selectedSucursal);
  }, [tarifas, selectedSucursal]);

  // Sets of uuid_tipo_vehiculo / uuid_tipo_tarifa (or
  // TIPO_NULL_SENTINEL_VEHICULO / TIPO_NULL_SENTINEL_TARIFA for NULL)
  // already in use by an OPEN tarifa for the selected branch. Used by
  // the CREATE flow to hide options that would collide with the
  // backend's ``tarifa_overlap`` guard (409). Note the tarifa
  // cell-key is the full tuple
  // ``(sucursal, tipo_vehiculo, tipo_tarifa)`` — this filter is
  // intentionally per-tipo (not per (v, t) tuple). The backend guard
  // is the safety net for the finer granularity.
  const tiposVehiculoEnUsoEnSucursal = useMemo(() => {
    const used = new Set<string>();
    for (const t of allFiltered) {
      used.add(t.uuid_tipo_vehiculo ?? '__VEHICULO_NULL__');
    }
    return used;
  }, [allFiltered]);
  const tiposTarifaEnUsoEnSucursal = useMemo(() => {
    const used = new Set<string>();
    for (const t of allFiltered) {
      used.add(t.uuid_tipo_tarifa ?? '__TARIFA_NULL__');
    }
    return used;
  }, [allFiltered]);

  const { versiones: historyVersiones } = useTarifasByKey(
    historyOpenFor === 'sin-sucursal' ? null : historyOpenFor,
  );

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  async function onSubmit(values: TarifaCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      // The form is single-tenant: the operator never picks a branch
      // (the topbar selector is the only source). We pin ``uuid_sucursal``
      // here so any caller-side drift between the topbar selection and
      // the form's default value can't reach the wire. If
      // ``selectedSucursal`` is null we refuse to submit (the page's
      // empty-state guard should prevent that path in practice).
      if (!selectedSucursal) {
        setErrorState({
          kind: 'network',
          message:
            'Seleccioná una sucursal activa antes de crear una tarifa.',
        });
        return;
      }
      const payload = { ...values, uuid_sucursal: selectedSucursal };
      if (editing !== null) {
        await updateTarifa(editing.uuid, payload);
      } else {
        await createTarifa(payload);
      }
      closeModal();
      await refresh();
    } catch (err) {
      setErrorState(mapError(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleEdit(t: Tarifa): void {
    setEditing(t);
    setCreating(false);
    setErrorState(null);
  }

  function handleToggleHistory(sucursalKey: string): void {
    setHistoryOpenFor((current) => (current === sucursalKey ? null : sucursalKey));
  }

  const activeSucursalLabel =
    sucursales?.find((s) => s.uuid === selectedSucursal)?.nombre ?? selectedSucursal ?? '';

  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-tarifas"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {t('tarifas.title', 'Tarifas')}
        </h1>
        <Button
          type="button"
          onClick={() => {
            setCreating(true);
            setEditing(null);
            setErrorState(null);
          }}
          data-testid="tarifa-new"
        >
          {t('tarifas.new', 'Nueva tarifa')}
        </Button>
      </header>

      {(creating || editing !== null) && (
        <FormModal
          open={true}
          onOpenChange={(open) => {
            if (!open) closeModal();
          }}
          title={
            editing !== null
              ? t('tarifas.editTitle', 'Editar tarifa')
              : t('tarifas.createTitle', 'Nueva tarifa')
          }
          description={t(
            'tarifas.modalDescription',
            'Cargá los datos. La tarifa pertenece a la sucursal elegida y entra en vigencia al instante seleccionado.',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'tarifa-form-modal' }}
        >
          {editing !== null ? (
            <TarifaFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTarifa={editing}
              onCancel={closeModal}
              sucursalActivaUuid={selectedSucursal}
              sucursalActivaNombre={activeSucursalLabel}
              tiposVehiculo={tiposVehiculo}
              tiposTarifa={tiposTarifa}
              tiposVehiculoEnUsoEnSucursal={tiposVehiculoEnUsoEnSucursal}
              tiposTarifaEnUsoEnSucursal={tiposTarifaEnUsoEnSucursal}
            />
          ) : (
            <TarifaFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialTarifa={null}
              onCancel={closeModal}
              sucursalActivaUuid={selectedSucursal}
              sucursalActivaNombre={activeSucursalLabel}
              tiposVehiculo={tiposVehiculo}
              tiposTarifa={tiposTarifa}
              tiposVehiculoEnUsoEnSucursal={tiposVehiculoEnUsoEnSucursal}
              tiposTarifaEnUsoEnSucursal={tiposTarifaEnUsoEnSucursal}
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
          {t('tarifas.loadError', 'No se pudieron cargar las tarifas.')}
        </p>
      )}

      {isLoading && tarifas.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('tarifas.loading', 'Cargando tarifas...')}
        </p>
      )}

      {!selectedSucursal ? (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="tarifas-active-empty-selection"
        >
          {t(
            'tarifas.tabs.activeEmpty',
            'Elegí una sucursal en el selector del topbar para ver sus tarifas.',
          )}
        </p>
      ) : (
        <ListContent
          tarifas={allFiltered}
          sucursales={sucursales}
          tiposVehiculo={tiposVehiculo}
          tiposTarifa={tiposTarifa}
          onEdit={handleEdit}
          onToggleHistory={handleToggleHistory}
          historyOpenFor={historyOpenFor}
          historyVersiones={historyVersiones}
          emptyMessage={t(
            'tarifas.tabs.activeEmptyForBranch',
            'Esta sucursal no tiene tarifas configuradas.',
          )}
        />
      )}
    </main>
  );
}
