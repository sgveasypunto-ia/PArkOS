/**
 * `<Cupos />` — admin screen for cupo (cantidad-vehiculos-sucursal) CRUD
 * (PR-D.4). Same shape as `<Tarifas />` with one extra typed error
 * class: ``CantidadBajoIngresosError`` (422) surfaces an actionable
 * message with ``activos`` and ``solicitada``.
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
import { CupoForm, CupoFormHarness } from '../components/CupoForm';

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
      message: `Hay ${err.activos} ingreso(s) activo(s); no podés bajar el cupo a ${err.solicitada}. Cerrá o anulá los ingresos primero.`,
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

export default function Cupos(): JSX.Element {
  const { t } = useTranslation();

  const { data: sucursales } = useSWR('/api/v1/empresa/sucursal?limit=200', async () =>
    listSucursales({ limit: 200 }),
  );

  const { cupos, refresh, isLoading, error } = useCantidadList();
  const [editing, setEditing] = useState<Cupo | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [historyOpenFor, setHistoryOpenFor] = useState<string | null>(null);

  const grouped = useMemo(() => {
    const map = new Map<string, Cupo[]>();
    for (const c of cupos) {
      const key = c.uuid_sucursal ?? 'sin-sucursal';
      const arr = map.get(key) ?? [];
      arr.push(c);
      map.set(key, arr);
    }
    return map;
  }, [cupos]);

  const { versiones: historyVersiones } = useCantidadByKey(
    historyOpenFor === 'sin-sucursal' ? null : historyOpenFor,
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
      if (editing !== null) {
        await updateCupo(editing.uuid, values);
      } else {
        await createCupo(values);
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
      data-testid="page-cupos"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('cupos.title', 'Cupos')}</h1>
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
      </header>

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
            <CupoForm
              form={undefined as never}
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialCupo={editing}
              onCancel={closeModal}
            />
          ) : (
            <CupoFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialCupo={null}
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
          {t('cupos.loadError', 'No se pudieron cargar los cupos.')}
        </p>
      )}

      {isLoading && cupos.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('cupos.loading', 'Cargando cupos...')}
        </p>
      )}

      {!isLoading && cupos.length === 0 && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="cupo-empty"
        >
          {t('cupos.empty', 'Aún no hay cupos configurados.')}
        </p>
      )}

      <div className="flex flex-col gap-4">
        {Array.from(grouped.entries()).map(([sucursalKey, items]) => {
          const sucursalNombre =
            sucursales?.find((s) => s.uuid === sucursalKey)?.nombre ??
            t('cupos.withoutSucursal', 'Sin sucursal');
          return (
            <Card
              key={sucursalKey}
              data-testid={`cupo-sucursal-group-${sucursalKey}`}
            >
              <CardHeader>
                <CardTitle>{sucursalNombre}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="px-3 py-2 text-right">Cantidad</th>
                      <th className="px-3 py-2 text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((cupo) => (
                      <tr
                        key={cupo.uuid}
                        data-testid={`cupo-row-${cupo.uuid}`}
                        className="border-b last:border-b-0"
                      >
                        <td className="px-3 py-2 text-right font-mono">
                          {cupo.cantidad ?? '—'}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditing(cupo);
                                setCreating(false);
                                setErrorState(null);
                              }}
                              data-testid={`cupo-edit-${cupo.uuid}`}
                            >
                              {t('cupos.action.edit', 'Editar')}
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
                              data-testid={`cupo-history-${cupo.uuid}`}
                            >
                              {historyOpenFor === sucursalKey
                                ? t('cupos.action.hideHistory', 'Ocultar histórico')
                                : t('cupos.action.history', 'Ver histórico')}
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
                      displayLabel={t('cupos.historyLabel', 'Cantidad')}
                      defaultExpanded
                      contentProps={{ 'data-testid': `cupo-history-${sucursalKey}` }}
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
