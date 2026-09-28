/**
 * `<ConfiguracionSeguridad />` — admin screen for security config.
 *
 * Includes a confirmation modal that fires when the user submits.
 * The values are operationally sensitive: changing the global
 * default ``minutos_bloqueo_login`` invalidates in-flight lockouts;
 * changing ``max_intentos_login`` affects every operator across the
 * tenant. The modal gives the operator one last look at the diff
 * before persisting.
 */
import * as React from 'react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';

import { FormModal } from '@/features/configuracion/components/FormModal';
import {
  createConfiguracionSeguridad,
  listConfiguracionSeguridad,
  updateConfiguracionSeguridad,
  type ConfiguracionSeguridad,
  type ConfiguracionSeguridadCreateInput,
} from '../api/configuracionSeguridadApi';
import {
  ConfiguracionSeguridadForm,
  ConfiguracionSeguridadFormHarness,
} from '../components/ConfiguracionSeguridadForm';

type ErrorState = { message: string } | null;

function mapError(err: unknown): ErrorState {
  const message = err instanceof Error ? err.message : 'Error desconocido';
  return { message };
}

function isGlobal(row: ConfiguracionSeguridad): boolean {
  return row.uuid_sucursal === null;
}

export default function ConfiguracionSeguridad(): JSX.Element {
  const { t } = useTranslation();

  const {
    data: rows = [],
    mutate: refresh,
    isLoading,
    error,
  } = useSWR<ConfiguracionSeguridad[]>(
    '/api/v1/configuracion/configuracion-seguridad?limit=200',
    async () => listConfiguracionSeguridad({ limit: 200 }),
  );

  const [editing, setEditing] = useState<ConfiguracionSeguridad | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  const [confirming, setConfirming] = useState(false);
  const [pendingValues, setPendingValues] =
    useState<ConfiguracionSeguridadCreateInput | null>(null);

  const globalRow = rows.find(isGlobal) ?? null;
  const overrides = rows.filter((r) => !isGlobal(r));

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  function onRequestSubmit(): void {
    // Validate via the schema first so the user sees errors before
    // the confirmation modal opens. The form fields are already
    // hooked into zodResolver, so we just trigger validation by
    // reading the current values.
    // The form's onSubmit onClick goes through here, so the form
    // has already prevented default. We capture the current values
    // and open the modal.
    setConfirming(true);
  }

  async function onConfirmSubmit(): Promise<void> {
    if (pendingValues === null) return;
    setSubmitting(true);
    setErrorState(null);
    try {
      if (editing !== null) {
        await updateConfiguracionSeguridad(editing.uuid, pendingValues);
      } else {
        await createConfiguracionSeguridad(pendingValues);
      }
      setConfirming(false);
      setPendingValues(null);
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
      data-testid="page-configuracion-seguridad"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {t('configuracionSeguridad.title', 'Configuración de seguridad')}
        </h1>
        <Button
          type="button"
          onClick={() => {
            setCreating(true);
            setEditing(null);
            setErrorState(null);
          }}
          data-testid="seguridad-new"
        >
          {t('configuracionSeguridad.new', 'Nueva configuración')}
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
              ? t('configuracionSeguridad.editTitle', 'Editar configuración de seguridad')
              : t('configuracionSeguridad.createTitle', 'Nueva configuración de seguridad')
          }
          description={t(
            'configuracionSeguridad.modalDescription',
            'Elegí el alcance y cargá los valores. Al hacer click en "Guardar" te mostraremos un resumen antes de aplicar.',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'seguridad-form-modal' }}
        >
          {editing !== null ? (
            <ConfiguracionSeguridadForm
              form={undefined as never}
              onSubmit={(values) => {
                setPendingValues(values);
                onRequestSubmit();
              }}
              onRequestSubmit={onRequestSubmit}
              isSubmitting={submitting}
              isUpdate
              initialSeguridad={editing}
              onCancel={closeModal}
            />
          ) : (
            <ConfiguracionSeguridadFormHarness
              onSubmit={(values) => {
                setPendingValues(values);
                onRequestSubmit();
              }}
              onRequestSubmit={onRequestSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialSeguridad={null}
              onCancel={closeModal}
            />
          )}
        </FormModal>
      )}

      <Dialog
        open={confirming}
        onOpenChange={(open) => {
          if (!open) {
            setConfirming(false);
            setPendingValues(null);
          }
        }}
        contentProps={
          { 'data-testid': 'seguridad-confirm-modal' } as React.HTMLAttributes<HTMLDivElement> & {
            'data-testid'?: string;
          }
        }
      >
        <div className="mx-auto flex max-w-md flex-col gap-4 rounded-xl border bg-card p-6 shadow-elevation-2">
          <DialogTitle>
            {t(
              'configuracionSeguridad.confirm.title',
              '¿Aplicar los cambios de seguridad?',
            )}
          </DialogTitle>
          <DialogDescription>
            {t(
              'configuracionSeguridad.confirm.description',
              'Cambiar las políticas de lockout invalida los intentos en curso. Los operadores actualmente bloqueados verán el nuevo tiempo al volver a intentar.',
            )}
          </DialogDescription>
          {pendingValues !== null && (
            <ul className="rounded-md bg-muted/40 p-3 text-sm">
              <li>
                {t(
                  'configuracionSeguridad.confirm.maxIntentos',
                  'Máx. intentos: {{n}}',
                  { n: pendingValues.max_intentos_login ?? '—' },
                )}
              </li>
              <li>
                {t(
                  'configuracionSeguridad.confirm.minutosBloqueo',
                  'Minutos de bloqueo: {{n}}',
                  { n: pendingValues.minutos_bloqueo_login ?? '—' },
                )}
              </li>
            </ul>
          )}
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setConfirming(false);
                setPendingValues(null);
              }}
              data-testid="seguridad-confirm-cancel"
            >
              {t('common.cancel', 'Cancelar')}
            </Button>
            <Button
              type="button"
              disabled={submitting}
              onClick={() => {
                void onConfirmSubmit();
              }}
              data-testid="seguridad-confirm-ok"
            >
              {submitting
                ? t('configuracionSeguridad.form.submitting', 'Guardando…')
                : t('configuracionSeguridad.confirm.ok', 'Aplicar')}
            </Button>
          </div>
        </div>
      </Dialog>

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('configuracionSeguridad.loadError', 'No se pudieron cargar las configuraciones.')}
        </p>
      )}

      {isLoading && rows.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('configuracionSeguridad.loading', 'Cargando configuraciones...')}
        </p>
      )}

      {!isLoading && rows.length === 0 && (
        <p
          role="status"
          aria-live="polite"
          className="text-sm text-muted-foreground"
          data-testid="seguridad-empty"
        >
          {t('configuracionSeguridad.empty', 'Aún no hay configuraciones de seguridad.')}
        </p>
      )}

      <div className="flex flex-col gap-4">
        {globalRow !== null && (
          <Card data-testid="seguridad-card-global">
            <CardHeader>
              <CardTitle>
                {t('configuracionSeguridad.titleGlobal', 'Default global')}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-3 py-2 text-right">Máx. intentos</th>
                    <th className="px-3 py-2 text-right">Min. bloqueo</th>
                    <th className="px-3 py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    data-testid={`seguridad-row-${globalRow.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-3 py-2 text-right font-mono">
                      {globalRow.max_intentos_login ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {globalRow.minutos_bloqueo_login ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditing(globalRow);
                          setCreating(false);
                          setErrorState(null);
                        }}
                        data-testid={`seguridad-edit-${globalRow.uuid}`}
                      >
                        {t('configuracionSeguridad.action.edit', 'Editar')}
                      </Button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {overrides.map((row) => (
          <Card
            key={row.uuid}
            data-testid={`seguridad-card-override-${row.uuid_sucursal ?? 'null'}`}
          >
            <CardHeader>
              <CardTitle>
                {t(
                  'configuracionSeguridad.titleOverride',
                  'Override · sucursal {{uuid}}',
                  { uuid: row.uuid_sucursal ?? '—' },
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-3 py-2 text-right">Máx. intentos</th>
                    <th className="px-3 py-2 text-right">Min. bloqueo</th>
                    <th className="px-3 py-2 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    data-testid={`seguridad-row-${row.uuid}`}
                    className="border-b last:border-b-0"
                  >
                    <td className="px-3 py-2 text-right font-mono">
                      {row.max_intentos_login ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {row.minutos_bloqueo_login ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setEditing(row);
                          setCreating(false);
                          setErrorState(null);
                        }}
                        data-testid={`seguridad-edit-${row.uuid}`}
                      >
                        {t('configuracionSeguridad.action.edit', 'Editar')}
                      </Button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
