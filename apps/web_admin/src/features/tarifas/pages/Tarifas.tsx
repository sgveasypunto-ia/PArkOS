/**
 * `<Tarifas />` — admin screen for tarifa CRUD (PR-D.3, PR2 of the
 * web_admin redesign).
 *
 * Layout:
 *   - Header: title + "Nueva tarifa" button.
 *   - TarifaForm modal (create + edit). Cancel dispatches close.
 *   - Tabs (PR2): "Todas las sucursales" (cross-branch, default) +
 *     "Mi sucursal activa" (filtered by `useSucursal().selected`).
 *   - Each tab renders the same grouped list of vigente tarifas.
 *     Each row has an "Editar" button (PUT) and a "Ver histórico"
 *     toggle that reveals the VersionHistoryPanel below the list.
 *
 * Container/presentational split: this file owns state, SWR mutations,
 * and error mapping. TarifaForm and VersionHistoryPanel are presentational.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  VersionHistoryPanel,
  type VersionHistoryItem,
} from '@/features/configuracion/components/VersionHistoryPanel';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';
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
import { TarifaForm, TarifaFormHarness } from '../components/TarifaForm';

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
  onEdit: (t: Tarifa) => void;
  onToggleHistory: (sucursalKey: string) => void;
  historyOpenFor: string | null;
  historyVersiones: Tarifa[];
  emptyMessage: string;
}

function ListContent({
  tarifas,
  sucursales,
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
                    <th className="px-3 py-2">Tipo vehículo</th>
                    <th className="px-3 py-2">Modalidad</th>
                    <th className="px-3 py-2 text-right">Valor</th>
                    <th className="px-3 py-2 text-right">Plena</th>
                    <th className="px-3 py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    key={tarifa.uuid}
                    data-testid={`tarifa-row-${tarifa.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-3 py-2 text-xs">
                      {tarifa.uuid_tipo_vehiculo ??
                        t('tarifas.tipoVehiculoAny', 'Cualquiera')}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      {tarifa.uuid_tipo_tarifa ??
                        t('tarifas.tipoTarifaAny', 'Cualquiera')}
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

  const { data: sucursales } = useSWR('/api/v1/empresa/sucursal?limit=200', async () =>
    listSucursales({ limit: 200 }),
  );

  const { tarifas, refresh, isLoading, error } = useTarifasList(null);
  const [editing, setEditing] = useState<Tarifa | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<string | null>(null);

  const allFiltered = useMemo(() => {
    // PR2: client-side filter by the picker selection. The full list is
    // already loaded once by `useTarifasList`; slicing it avoids a
    // second round-trip and keeps the tab snappy when toggling.
    if (!selectedSucursal) return tarifas;
    return tarifas.filter((tt) => tt.uuid_sucursal === selectedSucursal);
  }, [tarifas, selectedSucursal]);

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
      if (editing !== null) {
        await updateTarifa(editing.uuid, values);
      } else {
        await createTarifa(values);
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
            <TarifaForm
              form={undefined as never}
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTarifa={editing}
              onCancel={closeModal}
            />
          ) : (
            <TarifaFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialTarifa={null}
              onCancel={closeModal}
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

      <Tabs defaultValue="all" data-testid="tarifas-tabs">
        <TabsList>
          <TabsTrigger value="all" data-testid="tarifas-tab-all">
            {t('tarifas.tabs.all', 'Todas las sucursales')}
          </TabsTrigger>
          <TabsTrigger
            value="active"
            data-testid="tarifas-tab-active"
            disabled={!selectedSucursal}
          >
            {t('tarifas.tabs.active', 'Mi sucursal activa')}
            {selectedSucursal && activeSucursalLabel && (
              <span className="text-muted-foreground ml-2 font-mono text-xs">
                · {activeSucursalLabel}
              </span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          <ListContent
            tarifas={tarifas}
            sucursales={sucursales}
            onEdit={handleEdit}
            onToggleHistory={handleToggleHistory}
            historyOpenFor={historyOpenFor}
            historyVersiones={historyVersiones}
            emptyMessage={t('tarifas.empty', 'Aún no hay tarifas configuradas.')}
          />
        </TabsContent>

        <TabsContent value="active">
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
        </TabsContent>
      </Tabs>
    </main>
  );
}
