/**
 * `<ConfiguracionSeguridad />` — admin screen for security config.
 *
 * Includes a confirmation modal that fires when the user submits.
 * The values are operationally sensitive: changing the global
 * default ``minutos_bloqueo_login`` invalidates in-flight lockouts;
 * changing ``max_intentos_login`` affects every operator across the
 * tenant. The modal gives the operator one last look at the diff
 * before persisting.
 *
 * PR2 of the web_admin redesign adds tabs:
 *   - "Global y overrides" (default) — cross-branch view as before.
 *   - "Mi sucursal activa" — calls `/configuracion-seguridad/efectiva
 *     ?uuid_sucursal=<selected>` so the admin sees the actual effective
 *     value (override OR global fallback) for the active branch in one
 *     click. The endpoint already exists in `configuracionSeguridadApi`.
 */
import * as React from 'react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { FormModal } from '@/features/configuracion/components/FormModal';
import { useSucursal } from '@/lib/sucursal-context';
import {
  createConfiguracionSeguridad,
  getConfiguracionSeguridadEfectiva,
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

function RowTable({
  row,
  testIdPrefix,
  onEdit,
}: {
  row: ConfiguracionSeguridad;
  testIdPrefix: string;
  onEdit: () => void;
}): JSX.Element {
  const { t } = useTranslation();
  return (
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
          data-testid={`${testIdPrefix}-row-${row.uuid}`}
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
              onClick={onEdit}
              data-testid={`${testIdPrefix}-edit-${row.uuid}`}
            >
              {t('configuracionSeguridad.action.edit', 'Editar')}
            </Button>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export default function ConfiguracionSeguridad(): JSX.Element {
  const { t } = useTranslation();
  const { selected: selectedSucursal } = useSucursal();

  const {
    data: rows = [],
    mutate: refresh,
    isLoading,
    error,
  } = useSWR<ConfiguracionSeguridad[]>(
    '/api/v1/configuracion/configuracion-seguridad?limit=200',
    async () => listConfiguracionSeguridad({ limit: 200 }),
  );

  // PR2: fetch the effective value for the active branch. The endpoint
  // resolves override + global fallback server-side, so the UI shows
  // what the operator actually experiences at login.
  const effectiveKey = selectedSucursal
    ? `/api/v1/configuracion/configuracion-seguridad/efectiva?uuid_sucursal=${encodeURIComponent(selectedSucursal)}`
    : null;
  const { data: effectiveRow, isLoading: effectiveLoading } = useSWR<ConfiguracionSeguridad | null | undefined>(
    effectiveKey,
    async (key: string) => {
      const params = new URLSearchParams(key.split('?')[1] ?? '');
      const uuid = params.get('uuid_sucursal');
      if (!uuid) return null;
      const row = await getConfiguracionSeguridadEfectiva(uuid);
      return row;
    },
    { revalidateOnFocus: false },
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

  const activeOverride = useMemo(() => {
    if (!selectedSucursal) return null;
    return overrides.find((o) => o.uuid_sucursal === selectedSucursal) ?? null;
  }, [overrides, selectedSucursal]);

  function closeModal(): void {
    setCreating(false);
    setEditing(null);
    setErrorState(null);
  }

  function onRequestSubmit(): void {
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

  function handleEdit(row: ConfiguracionSeguridad): void {
    setEditing(row);
    setCreating(false);
    setErrorState(null);
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

      <Tabs defaultValue="all" data-testid="seguridad-tabs">
        <TabsList>
          <TabsTrigger value="all" data-testid="seguridad-tab-all">
            {t('configuracionSeguridad.tabs.all', 'Global y overrides')}
          </TabsTrigger>
          <TabsTrigger
            value="active"
            data-testid="seguridad-tab-active"
            disabled={!selectedSucursal}
          >
            {t('configuracionSeguridad.tabs.active', 'Efectiva en mi sucursal')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          {!isLoading && rows.length === 0 ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="seguridad-empty"
            >
              {t('configuracionSeguridad.empty', 'Aún no hay configuraciones de seguridad.')}
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {globalRow !== null && (
                <Card data-testid="seguridad-card-global">
                  <CardHeader>
                    <CardTitle>
                      {t('configuracionSeguridad.titleGlobal', 'Default global')}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <RowTable
                      row={globalRow}
                      testIdPrefix="seguridad"
                      onEdit={() => handleEdit(globalRow)}
                    />
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
                    <RowTable
                      row={row}
                      testIdPrefix="seguridad"
                      onEdit={() => handleEdit(row)}
                    />
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="active">
          {!selectedSucursal ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="seguridad-active-empty-selection"
            >
              {t(
                'configuracionSeguridad.tabs.activeEmpty',
                'Elegí una sucursal en el selector del topbar para ver la configuración efectiva.',
              )}
            </p>
          ) : effectiveLoading ? (
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {t('configuracionSeguridad.loading', 'Cargando configuraciones...')}
            </p>
          ) : effectiveRow === null || effectiveRow === undefined ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="seguridad-active-empty"
            >
              {t(
                'configuracionSeguridad.tabs.activeNoGlobal',
                'No hay default global todavía. Creá uno en "Global y overrides".',
              )}
            </p>
          ) : (
            <Card data-testid="seguridad-card-active">
              <CardHeader>
                <CardTitle>
                  {activeOverride !== null
                    ? t('configuracionSeguridad.titleOverride', 'Override · sucursal {{uuid}}', {
                        uuid: selectedSucursal,
                      })
                    : t(
                        'configuracionSeguridad.tabs.activeFromGlobal',
                        'Heredada del default global',
                      )}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <RowTable
                  row={effectiveRow}
                  testIdPrefix="seguridad"
                  onEdit={() => activeOverride !== null && handleEdit(activeOverride)}
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </main>
  );
}
