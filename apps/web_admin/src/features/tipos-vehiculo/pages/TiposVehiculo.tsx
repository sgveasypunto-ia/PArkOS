/**
 * `<TiposVehiculo />` — admin screen for tipo-vehiculo CRUD (PR-D).
 *
 * Mismo shape que `<Tarifas />` y `<Cupos />` con un solo campo
 * (lowercase por convención del seed). Sin guards typed — el factory
 * expone el C+Q+U genérico; los errores 5xx caen a un mensaje
 * genérico en el FormModal.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { FormModal } from '@/features/configuracion/components/FormModal';
import { listTiposVehiculo, type TipoVehiculo } from '../api/tiposVehiculoApi';
import {
  createTipoVehiculo,
  updateTipoVehiculo,
  type TipoVehiculoCreateInput,
} from '../api/tiposVehiculoApi';
import { TipoVehiculoFormHarness } from '../components/TipoVehiculoForm';

type ErrorState = { message: string } | null;

/**
 * Minimal 409 detail mapping, mirroring `CatalogEditor.tsx::mapConflictError`
 * for the same backend codes (`catalogos.py`'s tipos-vehiculo dedicated
 * router). This page's `tiposVehiculoApi.ts` throws a plain `Error` whose
 * `.message` embeds the raw response body (`"... -> 409: {json}"`), so the
 * code is extracted from that tail instead of a typed `ParkosHttpError`.
 */
function mapError(err: unknown): ErrorState {
  const message = err instanceof Error ? err.message : 'Error desconocido';
  const bodyStart = message.indexOf('{');
  if (bodyStart !== -1) {
    try {
      const parsed = JSON.parse(message.slice(bodyStart)) as {
        detail?: { error?: string };
      };
      if (parsed.detail?.error === 'catalogo_duplicado_vigente') {
        return { message: 'Ya existe una versión vigente con ese mismo valor.' };
      }
      if (parsed.detail?.error === 'tipos_vehiculo_max_reached') {
        return { message: 'Ya se alcanzó el máximo de 5 tipos de vehículo activos.' };
      }
    } catch {
      // Not JSON (or unknown shape) — fall through to the raw message.
    }
  }
  return { message };
}

export default function TiposVehiculo(): JSX.Element {
  const { t } = useTranslation();

  // useSWR is fine here: this catalog has a HARDCODED_CATALOG fallback
  // inside `useTiposVehiculo`, so a transient failure still renders the
  // list. We use SWR directly for the list + refetch after mutations.
  const {
    data: tipos = [],
    mutate: refresh,
    isLoading,
    error,
  } = useSWR<TipoVehiculo[]>('/api/v1/catalogos/tipos-vehiculo?limit=200', async () =>
    listTiposVehiculo({ limit: 200 }),
  );

  // 5-type cap mirrored from the backend (catalogos.py:cap on POST →
  // 409 ``tipos_vehiculo_max_reached``). Editing existing canonical
  // tipos is still allowed; only creation of a 6th tipo is blocked.
  const TIPOS_MAX = 5;
  const atCap = tipos.length >= TIPOS_MAX;

  const [editing, setEditing] = useState<TipoVehiculo | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  async function onSubmit(values: TipoVehiculoCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      if (editing !== null) {
        await updateTipoVehiculo(editing.uuid, values);
      } else {
        await createTipoVehiculo(values);
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
      data-testid="page-tipos-vehiculo"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {t('tiposVehiculo.title', 'Tipos de vehículo')}
        </h1>
        <div className="flex items-center gap-2">
          {atCap && (
            <span
              className="text-xs text-muted-foreground"
              data-testid="tipo-vehiculo-cap-notice"
              title={t(
                'tiposVehiculo.capReachedTitle',
                'Máximo de 5 tipos activos alcanzado',
              )}
            >
              {t('tiposVehiculo.capReached', '5/5 tipos activos')}
            </span>
          )}
          <Button
            type="button"
            onClick={() => {
              setCreating(true);
              setEditing(null);
              setErrorState(null);
            }}
            disabled={atCap}
            data-testid="tipo-vehiculo-new"
          >
            {t('tiposVehiculo.new', 'Nuevo tipo de vehículo')}
          </Button>
        </div>
      </header>

      {(creating || editing !== null) && (
        <FormModal
          open={true}
          onOpenChange={(open) => {
            if (!open) closeModal();
          }}
          title={
            editing !== null
              ? t('tiposVehiculo.editTitle', 'Editar tipo de vehículo')
              : t('tiposVehiculo.createTitle', 'Nuevo tipo de vehículo')
          }
          description={t(
            'tiposVehiculo.modalDescription',
            'Ingresá el nombre. El seed canónico usa lowercase (carro, moto, bicicleta, patineta, otro).',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'tipo-vehiculo-form-modal' }}
        >
          {editing !== null ? (
            <TipoVehiculoFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTipoVehiculo={editing}
              onCancel={closeModal}
            />
          ) : (
            <TipoVehiculoFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialTipoVehiculo={null}
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
          {t('tiposVehiculo.loadError', 'No se pudieron cargar los tipos de vehículo.')}
        </p>
      )}

      {isLoading && tipos.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('tiposVehiculo.loading', 'Cargando tipos de vehículo...')}
        </p>
      )}

      {!isLoading && tipos.length === 0 && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="tipo-vehiculo-empty"
        >
          {t('tiposVehiculo.empty', 'Aún no hay tipos de vehículo configurados.')}
        </p>
      )}

      <div className="flex flex-col gap-4">
        <Card data-testid="tipo-vehiculo-card">
          <CardHeader>
            <CardTitle>
              {t('tiposVehiculo.title', 'Tipos de vehículo')}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2">Estado</th>
                  <th className="px-3 py-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {tipos.map((tipo) => (
                  <tr
                    key={tipo.uuid}
                    data-testid={`tipo-vehiculo-row-${tipo.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-3 py-2 font-mono text-sm">
                      {tipo.tipo ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground text-xs">
                      {tipo.estado}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditing(tipo);
                          setCreating(false);
                          setErrorState(null);
                        }}
                        data-testid={`tipo-vehiculo-edit-${tipo.uuid}`}
                      >
                        {t('tiposVehiculo.action.edit', 'Editar')}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
