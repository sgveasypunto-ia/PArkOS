/**
 * `<TipoTarifa />` — admin screen for tipo-tarifa CRUD (PR-D). Mismo
 * shape que `<TiposVehiculo />`: un solo campo ``tipo``, sin guards
 * typed (el factory expone el C+Q+U genérico).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  createTipoTarifa,
  listTipoTarifa,
  updateTipoTarifa,
  type TipoTarifa,
  type TipoTarifaCreateInput,
} from '../api/tipoTarifaApi';
import { TipoTarifaFormHarness } from '../components/TipoTarifaForm';

type ErrorState = { message: string } | null;

function mapError(err: unknown): ErrorState {
  const message = err instanceof Error ? err.message : 'Error desconocido';
  return { message };
}

export default function TipoTarifa(): JSX.Element {
  const { t } = useTranslation();

  const {
    data: tipos = [],
    mutate: refresh,
    isLoading,
    error,
  } = useSWR<TipoTarifa[]>('/api/v1/catalogos/tipo-tarifa?limit=200', async () =>
    listTipoTarifa({ limit: 200 }),
  );

  const [editing, setEditing] = useState<TipoTarifa | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  async function onSubmit(values: TipoTarifaCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      if (editing !== null) {
        await updateTipoTarifa(editing.uuid, values);
      } else {
        await createTipoTarifa(values);
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
      data-testid="page-tipo-tarifa"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {t('tipoTarifa.title', 'Modalidades de tarifa')}
        </h1>
        <Button
          type="button"
          onClick={() => {
            setCreating(true);
            setEditing(null);
            setErrorState(null);
          }}
          data-testid="tipo-tarifa-new"
        >
          {t('tipoTarifa.new', 'Nueva modalidad')}
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
              ? t('tipoTarifa.editTitle', 'Editar modalidad')
              : t('tipoTarifa.createTitle', 'Nueva modalidad')
          }
          description={t(
            'tipoTarifa.modalDescription',
            'Ingresá el nombre. El seed canónico usa lowercase (hora, fraccion, plena, nocturna).',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'tipo-tarifa-form-modal' }}
        >
          {editing !== null ? (
            <TipoTarifaFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTipoTarifa={editing}
              onCancel={closeModal}
            />
          ) : (
            <TipoTarifaFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialTipoTarifa={null}
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
          {t('tipoTarifa.loadError', 'No se pudieron cargar las modalidades.')}
        </p>
      )}

      {isLoading && tipos.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('tipoTarifa.loading', 'Cargando modalidades...')}
        </p>
      )}

      {!isLoading && tipos.length === 0 && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="tipo-tarifa-empty"
        >
          {t('tipoTarifa.empty', 'Aún no hay modalidades configuradas.')}
        </p>
      )}

      <div className="flex flex-col gap-4">
        <Card data-testid="tipo-tarifa-card">
          <CardHeader>
            <CardTitle>{t('tipoTarifa.title', 'Modalidades de tarifa')}</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-3 py-2">Modalidad</th>
                  <th className="px-3 py-2">Estado</th>
                  <th className="px-3 py-2 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {tipos.map((tipo) => (
                  <tr
                    key={tipo.uuid}
                    data-testid={`tipo-tarifa-row-${tipo.uuid}`}
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
                        data-testid={`tipo-tarifa-edit-${tipo.uuid}`}
                      >
                        {t('tipoTarifa.action.edit', 'Editar')}
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
