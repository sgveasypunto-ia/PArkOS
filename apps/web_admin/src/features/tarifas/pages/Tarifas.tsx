/**
 * `<Tarifas />` — admin screen for tarifa CRUD (PR-D.3).
 *
 * Layout:
 *   - Header: title + "Nueva tarifa" button.
 *   - TarifaForm modal (create + edit). Cancel dispatches close.
 *   - List of vigente tarifas grouped by sucursal. Each row has an
 *     "Editar" button (PUT) and a "Ver histórico" toggle that reveals
 *     the VersionHistoryPanel below the list.
 *
 * Container/presentational split: this file owns state, SWR mutations,
 * and error mapping. TarifaForm and VersionHistoryPanel are presentational.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  VersionHistoryPanel,
  type VersionHistoryItem,
} from '@/features/configuracion/components/VersionHistoryPanel';
import { listSucursales } from '@/features/sucursales/api/sucursalesApi';

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

export default function Tarifas(): JSX.Element {
  const { t } = useTranslation();

  const { data: sucursales } = useSWR('/api/v1/empresa/sucursal?limit=200', async () =>
    listSucursales({ limit: 200 }),
  );

  const { tarifas, refresh, isLoading, error } = useTarifasList(null);
  const [editing, setEditing] = useState<Tarifa | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, Tarifa[]>();
    for (const t of tarifas) {
      const key = t.uuid_sucursal ?? 'sin-sucursal';
      const arr = map.get(key) ?? [];
      arr.push(t);
      map.set(key, arr);
    }
    return map;
  }, [tarifas]);

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

      {!isLoading && tarifas.length === 0 && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="tarifa-empty"
        >
          {t('tarifas.empty', 'Aún no hay tarifas configuradas.')}
        </p>
      )}

      <div className="flex flex-col gap-4">
        {Array.from(grouped.entries()).map(([sucursalKey, items]) => {
          const sucursalNombre =
            sucursales?.find((s) => s.uuid === sucursalKey)?.nombre ??
            t('tarifas.withoutSucursal', 'Sin sucursal');
          return (
            <Card
              key={sucursalKey}
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
                    {items.map((tarifa) => (
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
                              onClick={() => {
                                setEditing(tarifa);
                                setCreating(false);
                                setErrorState(null);
                              }}
                              data-testid={`tarifa-edit-${tarifa.uuid}`}
                            >
                              {t('tarifas.action.edit', 'Editar')}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                setHistoryOpenFor((current) =>
                                  current === sucursalKey ? null : sucursalKey,
                                )
                              }
                              data-testid={`tarifa-history-${tarifa.uuid}`}
                            >
                              {historyOpenFor === sucursalKey
                                ? t('tarifas.action.hideHistory', 'Ocultar histórico')
                                : t('tarifas.action.history', 'Ver histórico')}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {historyOpenFor === sucursalKey && (
                  <div className="border-t p-4">
                    <VersionHistoryPanel
                      versions={historyVersiones.map(toHistoryItem)}
                      displayLabel={t('tarifas.historyLabel', 'Valor')}
                      defaultExpanded
                      contentProps={{ 'data-testid': `tarifa-history-${sucursalKey}` }}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </main>
  );
}
