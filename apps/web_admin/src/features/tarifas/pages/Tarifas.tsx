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
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSWRConfig } from 'swr';

import { PageHeader } from '@/components/layout/PageHeader';
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
  createTarifaBatch,
  updateTarifa,
  TarifaConflictError,
  TarifaOverlapError,
  TarifaSucursalInmutableError,
  TarifaValidationError,
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
import { formatTarifaValor } from '../lib/formatTarifaValor';
import { TarifaFormHarness } from '../components/TarifaForm';

type ErrorState =
  | { kind: 'overlap'; message: string }
  | { kind: 'inmutable'; message: string }
  | { kind: 'validation'; message: string; fieldErrors: ReadonlyArray<{ path: string; message: string }> }
  | { kind: 'network'; message: string }
  | null;

function mapError(err: unknown): ErrorState {
  // TarifaValidationError -- the local Zod schema rejected the payload
  // BEFORE the HTTP call. Surface a translated message and expose the
  // structured ``issues`` array so the form can mark individual fields
  // (currently the alert shows the message; per-field RHF ``setError``
  // wiring is the natural follow-up if the modal layout demands it).
  if (err instanceof TarifaValidationError) {
    const fieldList = err.issues
      .map((i) => `${i.path}: ${i.message}`)
      .join(' / ');
    return {
      kind: 'validation',
      message: `Revisá los campos del formulario (${fieldList}).`,
      fieldErrors: err.issues,
    };
  }
  // TarifaConflictError -- 409 from the backend (DB-level race that
  // slipped past ``assert_no_overlap``). Distinguished from the
  // pre-check overlap via the ``constraint`` field. We keep the
  // ``overlap`` slot for compatibility with the existing alert UI.
  if (err instanceof TarifaConflictError) {
    return {
      kind: 'overlap',
      message: err.constraint
        ? `Conflicto con una tarifa existente (constraint: ${err.constraint}). Elegí otro instante o actualizá la existente.`
        : 'Conflicto con una tarifa existente. Elegí otro instante o actualizá la existente.',
    };
  }
  // TarifaOverlapError -- the typed error class kept for the FE
  // pre-flight error (the 409 path the FE used to map). The PR1
  // backend now uses the same shape (tarifa_overlap) for both the
  // pre-check and the DB-race path; we map both into the same
  // ``TarifaConflictError`` shape (above) at the API layer. The
  // legacy class is kept here so older callers (or third-party
  // consumers of this file) still parse.
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
  onToggleHistory: (sucursal: string, tipoVehiculo: string | null) => void;
  historyOpenFor: { sucursal: string; tipoVehiculo: string | null } | null;
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
        const tipoVehiculoKey = g.uuid_tipo_vehiculo ?? null;
        const isHistoryOpen =
          historyOpenFor !== null &&
          historyOpenFor.sucursal === sucursalKey &&
          historyOpenFor.tipoVehiculo === tipoVehiculoKey;
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
                      {formatTarifaValor(g.hora.valor)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {formatTarifaValor(g.fraccion.valor)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {formatTarifaValor(g.plena.valor)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {formatTarifaValor(g.nocturna.valor)}
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
                          onClick={() => onToggleHistory(sucursalKey, tipoVehiculoKey)}
                          data-testid={`tarifa-history-${grupoKey}`}
                        >
                          {isHistoryOpen
                            ? t('tarifas.action.hideHistory', 'Ocultar histórico')
                            : t('tarifas.action.history', 'Ver histórico')}
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
  const { mutate: globalMutate } = useSWRConfig();
  const [editingGrupo, setEditingGrupo] = useState<TarifaAgrupada | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<
    { sucursal: string; tipoVehiculo: string | null } | null
  >(null);

  // Best-effort revalidation of the by-key cache. ``useTarifasByKey`` is
  // a 4-way fan-out — one cache per ``TIPO_TARIFA_UUIDS`` modalidad
  // (hora/fraccion/plena/nocturna) for the same business key
  // ``(sucursal, uuid_tipo_vehiculo)``. The PUT/POST only changes the
  // rows for the modalidades the operator touched, but invalidating
  // all four is the cheap and correct call: the by-key list panel
  // merges the four caches for the open panel, and any stale entry
  // would silently mask the new version until F5. Mirrors the cupos
  // fix (see ``Cupos.tsx::invalidateByKey``) — same bug class, same
  // resolution.
  const invalidateByKey = useCallback(
    async (sucursal: string, tipoVehiculo: string | null): Promise<void> => {
      await Promise.all(
        (Object.values(TIPO_TARIFA_UUIDS) as string[]).map((uuidTipoTarifa) =>
          globalMutate([
            '/api/v1/empresa/tarifas-sucursal/by-key',
            sucursal,
            tipoVehiculo,
            uuidTipoTarifa,
          ]),
        ),
      );
    },
    [globalMutate],
  );

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

  // Ver histórico: the grouped list shows one row per (sucursal,
  // tipo_vehiculo) with 4 modalidad columns, but the by-key endpoint's
  // business key is (sucursal, tipo_vehiculo, tipo_tarifa) -- omitting
  // tipo_tarifa does NOT mean "any modalidad", it means "match the rows
  // where tipo_tarifa IS NULL" (`is_not_distinct_from`, same NULL-is-a-
  // valid-business-value semantics `tipo_vehiculo` uses for the
  // "Cualquiera" case). So showing the full timeline for a grouped row
  // means querying each of the 4 canonical modalidades explicitly and
  // merging, not a single call with tipo_tarifa omitted.
  const historySucursal =
    historyOpenFor === null || historyOpenFor.sucursal === 'sin-sucursal'
      ? null
      : historyOpenFor.sucursal;
  const historyTipoVehiculo = historyOpenFor?.tipoVehiculo ?? null;
  const { versiones: historyHora } = useTarifasByKey(
    historySucursal,
    historyTipoVehiculo,
    TIPO_TARIFA_UUIDS.hora,
  );
  const { versiones: historyFraccion } = useTarifasByKey(
    historySucursal,
    historyTipoVehiculo,
    TIPO_TARIFA_UUIDS.fraccion,
  );
  const { versiones: historyPlena } = useTarifasByKey(
    historySucursal,
    historyTipoVehiculo,
    TIPO_TARIFA_UUIDS.plena,
  );
  const { versiones: historyNocturna } = useTarifasByKey(
    historySucursal,
    historyTipoVehiculo,
    TIPO_TARIFA_UUIDS.nocturna,
  );
  const historyVersiones = useMemo(
    () =>
      [...historyHora, ...historyFraccion, ...historyPlena, ...historyNocturna].sort(
        (a, b) => b.vigente_desde.localeCompare(a.vigente_desde),
      ),
    [historyHora, historyFraccion, historyPlena, historyNocturna],
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
        // CREATE: ONE atomic POST /batch. The form's RHF refine
        // (HU-tarifas-batch) guarantees every ``valor_*`` is a valid
        // decimal string at submit time -- no more ``?? '0'`` fallback
        // that used to silently produce a partial cell. The batch
        // endpoint validates the 4 canonical modalidades and rolls
        // back atomically on any failure (no partial row, no orphan).
        //
        // We map each input to its corresponding modalidad via
        // ``TIPO_TARIFA_UUIDS`` (the same canonical set the backend
        // enforces in ``_TARIFA_MODALIDADES_CANONICAL``).
        const valorPorModalidad: Record<string, string | null> = {
          [TIPO_TARIFA_UUIDS.hora]: values.valor_hora ?? null,
          [TIPO_TARIFA_UUIDS.fraccion]: values.valor_fraccion ?? null,
          [TIPO_TARIFA_UUIDS.plena]: values.valor_plena ?? null,
          [TIPO_TARIFA_UUIDS.nocturna]: values.valor_nocturna ?? null,
        };
        const items: Array<{ uuid_tipo_tarifa: string; valor: string; valor_plena: string | null }> = (
          Object.keys(valorPorModalidad) as string[]
        )
          .map((uuidTipoTarifa) => {
            const valor = valorPorModalidad[uuidTipoTarifa];
            if (valor === null) return null;
            return {
              uuid_tipo_tarifa: uuidTipoTarifa,
              valor,
              valor_plena: uuidTipoTarifa === TIPO_TARIFA_UUIDS.plena ? valor : null,
            };
          })
          .filter(
            (it): it is { uuid_tipo_tarifa: string; valor: string; valor_plena: string | null } =>
              it !== null,
          );
        await createTarifaBatch({
          uuid_sucursal: selectedSucursal,
          uuid_tipo_vehiculo: values.uuid_tipo_vehiculo,
          vigente_desde: values.vigente_desde,
          items,
        });
      }
      closeModal();
      // ``refresh()`` only invalidates the 'tarifas-list' key; the
      // by-key cache for the edited cell must be invalidated
      // explicitly so the "Ver histórico" panel picks up the new
      // version without F5 (see Cupos.tsx::onSubmit for the matching
      // fix — same bug class).
      await Promise.all([
        refresh(),
        invalidateByKey(selectedSucursal, values.uuid_tipo_vehiculo),
      ]);
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
      data-testid="page-tarifas"
    >
      <PageHeader
        title={t('tarifas.title', 'Tarifas')}
        actions={
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
        }
      />

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
              initialTarifaAgrupada={null}
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
    </div>
  );
}