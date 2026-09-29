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
 * The list shows ONE row per (sucursal, tipo_vehiculo) with four
 * columns (hora, fraccion, plena, nocturna). The backend stores
 * tarifas as 4 separate rows per (sucursal, tipo_vehiculo) — one
 * per modalidad — so the page flattens the rows on read via
 * ``agruparTarifas``.
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
import { useSucursal } from '@/lib/sucursal-context';

import {
  createTarifa,
  updateTarifa,
  TarifaOverlapError,
  TarifaSucursalInmutableError,
  type Tarifa,
  type TarifaCreateInput,
} from '../api/tarifasApi';
import {
  agruparTarifas,
  TIPO_TARIFA_UUIDS,
  type TarifaAgrupada,
} from '../api/tarifaAgrupada';
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

interface ListContentProps {
  grupos: TarifaAgrupada[];
  sucursales: Array<{ uuid: string; nombre: string | null }> | undefined;
  tiposVehiculo: Array<{ uuid: string; tipo: string | null }>;
  onEdit: (g: TarifaAgrupada) => void;
  onToggleHistory: (sucursalKey: string) => void;
  historyOpenFor: string | null;
  historyVersiones: Tarifa[];
  emptyMessage: string;
}

function ListContent({
  grupos,
  sucursales,
  tiposVehiculo,
  onEdit,
  onToggleHistory,
  historyOpenFor,
  historyVersiones,
  emptyMessage,
}: ListContentProps): JSX.Element {
  const { t } = useTranslation();

  if (grupos.length === 0) {
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
      {grupos.map((g) => {
        const sucursalKey = g.uuid_sucursal ?? 'sin-sucursal';
        const sucursalNombre =
          sucursales?.find((s) => s.uuid === sucursalKey)?.nombre ??
          t('tarifas.withoutSucursal', 'Sin sucursal');
        const tipoVehiculoNombre = g.uuid_tipo_vehiculo
          ? (tiposVehiculo.find((tv) => tv.uuid === g.uuid_tipo_vehiculo)?.tipo ??
            t('tarifas.unknownTipoVehiculo', 'Desconocido'))
          : t('tarifas.tipoVehiculoAny', 'Cualquiera');
        const grupoKey = `${g.uuid_sucursal}|${g.uuid_tipo_vehiculo}|${g.vigente_desde}`;
        return (
          <Card
            key={grupoKey}
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
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.valorHora', 'Hora')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.valorFraccion', 'Fracción')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.valorPlena', 'Plena')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.valorNocturna', 'Nocturna')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('tarifas.col.acciones', 'Acciones')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    key={grupoKey}
                    data-testid={`tarifa-row-${grupoKey}`}
                    className="border-b last:border-b-0"
                  >
                    <td
                      className="px-3 py-2 text-xs"
                      data-testid={`tarifa-tipo-${grupoKey}`}
                    >
                      {tipoVehiculoNombre}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {g.hora.valor ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {g.fraccion.valor ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {g.plena.valor ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {g.nocturna.valor ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => onEdit(g)}
                          data-testid={`tarifa-edit-${grupoKey}`}
                        >
                          {t('tarifas.action.edit', 'Editar')}
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onToggleHistory(sucursalKey)}
                          data-testid={`tarifa-history-${grupoKey}`}
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

function toHistoryItem(t: Tarifa): VersionHistoryItem {
  return {
    uuid: t.uuid,
    display: t.valor ?? '—',
    vigente_desde: t.vigente_desde,
    vigente_hasta: t.vigente_hasta,
    estado: t.estado,
  };
}

export default function Tarifas(): JSX.Element {
  const { t } = useTranslation();
  const { selected: selectedSucursal } = useSucursal();

  const { sucursales } = useSucursalesDirectorio();

  const { tarifas, refresh, isLoading, error } = useTarifasList(null);
  const { tipos: tiposVehiculo } = useTiposVehiculo();
  const [editingGrupo, setEditingGrupo] = useState<TarifaAgrupada | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<string | null>(null);

  const allFiltered = useMemo(() => {
    if (!selectedSucursal) return [];
    return tarifas.filter((tt) => tt.uuid_sucursal === selectedSucursal);
  }, [tarifas, selectedSucursal]);

  // Flatten the 4 rows per (sucursal, tipo_vehiculo) into a single
  // ``TarifaAgrupada`` for the list.
  const grupos = useMemo(() => agruparTarifas(allFiltered), [allFiltered]);

  // Cell-key for tarifas is now (sucursal, tipo_vehiculo).
  const tiposVehiculoEnUsoEnSucursal = useMemo(() => {
    const used = new Set<string>();
    for (const g of grupos) {
      used.add(g.uuid_tipo_vehiculo || '__VEHICULO_NULL__');
    }
    return used;
  }, [grupos]);

  const { versiones: historyVersiones } = useTarifasByKey(
    historyOpenFor === 'sin-sucursal' ? null : historyOpenFor,
  );

  function closeModal(): void {
    setCreating(false);
    setEditingGrupo(null);
    setErrorState(null);
  }

  async function onSubmit(values: TarifaCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      if (!selectedSucursal) {
        setErrorState({
          kind: 'network',
          message:
            'Seleccioná una sucursal activa antes de crear una tarifa.',
        });
        return;
      }
      if (!values.uuid_tipo_vehiculo) {
        setErrorState({
          kind: 'network',
          message: 'Seleccioná un tipo de vehículo antes de crear la tarifa.',
        });
        return;
      }
      if (editingGrupo !== null) {
        // EDIT: split PUT (modalidad exists in DB) vs CREATE
        // (modalidad is brand-new — operator added a value for it).
        const base = {
          uuid_sucursal: selectedSucursal,
          uuid_tipo_vehiculo: values.uuid_tipo_vehiculo,
          vigente_desde: values.vigente_desde,
        };
        const updates: Array<{
          uuid: string;
          uuid_tipo_tarifa: string;
          valor: string;
          valor_plena: string | null;
        }> = [];
        const creates: Array<{
          uuid_tipo_tarifa: string;
          valor: string;
          valor_plena: string | null;
        }> = [];

        // hora
        if (editingGrupo.hora.uuid && values.valor_hora) {
          updates.push({
            uuid: editingGrupo.hora.uuid,
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.hora,
            valor: values.valor_hora,
            valor_plena: null,
          });
        } else if (!editingGrupo.hora.uuid && values.valor_hora) {
          creates.push({
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.hora,
            valor: values.valor_hora,
            valor_plena: null,
          });
        }

        // fraccion
        if (editingGrupo.fraccion.uuid && values.valor_fraccion) {
          updates.push({
            uuid: editingGrupo.fraccion.uuid,
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion,
            valor: values.valor_fraccion,
            valor_plena: null,
          });
        } else if (!editingGrupo.fraccion.uuid && values.valor_fraccion) {
          creates.push({
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion,
            valor: values.valor_fraccion,
            valor_plena: null,
          });
        }

        // plena
        if (editingGrupo.plena.uuid && values.valor_plena) {
          updates.push({
            uuid: editingGrupo.plena.uuid,
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena,
            valor: values.valor_plena,
            valor_plena: null,
          });
        } else if (!editingGrupo.plena.uuid && values.valor_plena) {
          creates.push({
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena,
            valor: values.valor_plena,
            valor_plena: null,
          });
        }

        // nocturna
        if (editingGrupo.nocturna.uuid && values.valor_nocturna) {
          updates.push({
            uuid: editingGrupo.nocturna.uuid,
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna,
            valor: values.valor_nocturna,
            valor_plena: null,
          });
        } else if (!editingGrupo.nocturna.uuid && values.valor_nocturna) {
          creates.push({
            uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna,
            valor: values.valor_nocturna,
            valor_plena: null,
          });
        }

        for (const it of updates) {
          await updateTarifa(it.uuid, {
            ...base,
            uuid_tipo_tarifa: it.uuid_tipo_tarifa,
            valor: it.valor,
            valor_plena: it.valor_plena,
          });
        }
        for (const it of creates) {
          await createTarifa({
            ...base,
            uuid_tipo_tarifa: it.uuid_tipo_tarifa,
            valor: it.valor,
            valor_plena: it.valor_plena,
          });
        }
      } else {
        // CREATE: 4 POSTs (one per modalidad).
        const base = {
          uuid_sucursal: selectedSucursal,
          uuid_tipo_vehiculo: values.uuid_tipo_vehiculo,
          vigente_desde: values.vigente_desde,
        };
        const items: Array<{ uuid_tipo_tarifa: string; valor: string; valor_plena: string | null }> = [
          { uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.hora, valor: values.valor_hora ?? '0', valor_plena: null },
          { uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.fraccion, valor: values.valor_fraccion ?? '0', valor_plena: null },
          { uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.plena, valor: values.valor_plena ?? '0', valor_plena: null },
          { uuid_tipo_tarifa: TIPO_TARIFA_UUIDS.nocturna, valor: values.valor_nocturna ?? '0', valor_plena: null },
        ];
        for (const it of items) {
          await createTarifa({
            ...base,
            uuid_tipo_tarifa: it.uuid_tipo_tarifa,
            valor: it.valor,
            valor_plena: it.valor_plena,
          });
        }
      }
      closeModal();
      await refresh();
    } catch (err) {
      setErrorState(mapError(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleEdit(g: TarifaAgrupada): void {
    setEditingGrupo(g);
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
            setEditingGrupo(null);
            setErrorState(null);
          }}
          data-testid="tarifa-new"
        >
          {t('tarifas.new', 'Nueva tarifa')}
        </Button>
      </header>

      {(creating || editingGrupo !== null) && (
        <FormModal
          open={true}
          onOpenChange={(open) => {
            if (!open) closeModal();
          }}
          title={
            editingGrupo !== null
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
          {editingGrupo !== null ? (
            <TarifaFormHarness
              key={`edit-${editingGrupo.uuid_sucursal}-${editingGrupo.uuid_tipo_vehiculo}-${editingGrupo.vigente_desde}`}
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTarifaAgrupada={editingGrupo}
              onCancel={closeModal}
              sucursalActivaUuid={selectedSucursal}
              sucursalActivaNombre={activeSucursalLabel}
              tiposVehiculo={tiposVehiculo}
              tiposVehiculoEnUsoEnSucursal={tiposVehiculoEnUsoEnSucursal}
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
              tiposVehiculoEnUsoEnSucursal={tiposVehiculoEnUsoEnSucursal}
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
          grupos={grupos}
          sucursales={sucursales}
          tiposVehiculo={tiposVehiculo}
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