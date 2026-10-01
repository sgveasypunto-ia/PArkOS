/**
 * `<ConfiguracionTolerancias />` — admin screen for tolerance config.
 *
 * Listado de filas agrupado por alcance (global vs per-branch). El
 * form tiene el toggle "Default global" vs "Override por sucursal"
 * (REQ-OP-12, SC-OP-06): el toggle setea ``uuid_sucursal = null`` o
 * el uuid elegido.
 *
 * PR2 of the web_admin redesign adds tabs so the admin can jump
 * straight to the override of the active branch without scrolling the
 * full override list. Filter is client-side (the full list is already
 * loaded by `useSWR`).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useSWR from 'swr';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { FormModal } from '@/features/configuracion/components/FormModal';
import { useSucursal } from '@/lib/sucursal-context';
import {
  createConfiguracionTolerancias,
  listConfiguracionTolerancias,
  updateConfiguracionTolerancias,
  type ConfiguracionTolerancias,
  type ConfiguracionToleranciasCreateInput,
} from '../api/configuracionToleranciasApi';
import {
  ConfiguracionToleranciasForm,
  ConfiguracionToleranciasFormHarness,
} from '../components/ConfiguracionToleranciasForm';

type ErrorState = { message: string } | null;

function mapError(err: unknown): ErrorState {
  const message = err instanceof Error ? err.message : 'Error desconocido';
  return { message };
}

function isGlobal(row: ConfiguracionTolerancias): boolean {
  return row.uuid_sucursal === null;
}

function RowTable({
  row,
  testIdPrefix,
  onEdit,
}: {
  row: ConfiguracionTolerancias;
  testIdPrefix: string;
  onEdit: () => void;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left">
          <th className="px-3 py-2 text-right">Efectivo</th>
          <th className="px-3 py-2 text-right">Datáfono</th>
          <th className="px-3 py-2 text-right">Acciones</th>
        </tr>
      </thead>
      <tbody>
        <tr
          data-testid={`${testIdPrefix}-row-${row.uuid}`}
          className="border-b last:border-b-0"
        >
          <td className="px-3 py-2 text-right font-mono">
            {row.tolerancia_efectivo ?? '—'}
          </td>
          <td className="px-3 py-2 text-right font-mono">
            {row.tolerancia_datafono ?? '—'}
          </td>
          <td className="px-3 py-2 text-right">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onEdit}
              data-testid={`${testIdPrefix}-edit-${row.uuid}`}
            >
              {t('configuracionTolerancias.action.edit', 'Editar')}
            </Button>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

export default function ConfiguracionTolerancias(): JSX.Element {
  const { t } = useTranslation();
  const { selected: selectedSucursal } = useSucursal();

  const {
    data: rows = [],
    mutate: refresh,
    isLoading,
    error,
  } = useSWR<ConfiguracionTolerancias[]>(
    '/api/v1/configuracion/configuracion-tolerancias?limit=200',
    async () => listConfiguracionTolerancias({ limit: 200 }),
  );

  const [editing, setEditing] = useState<ConfiguracionTolerancias | null>(null);
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);

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

  async function onSubmit(values: ConfiguracionToleranciasCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      if (editing !== null) {
        await updateConfiguracionTolerancias(editing.uuid, values);
      } else {
        await createConfiguracionTolerancias(values);
      }
      closeModal();
      await refresh();
    } catch (err) {
      setErrorState(mapError(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleEdit(row: ConfiguracionTolerancias): void {
    setEditing(row);
    setCreating(false);
    setErrorState(null);
  }

  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-configuracion-tolerancias"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {t('configuracionTolerancias.title', 'Tolerancias de caja')}
        </h1>
        <Button
          type="button"
          onClick={() => {
            setCreating(true);
            setEditing(null);
            setErrorState(null);
          }}
          data-testid="tolerancia-new"
        >
          {t('configuracionTolerancias.new', 'Nueva tolerancia')}
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
              ? t('configuracionTolerancias.editTitle', 'Editar tolerancia')
              : t('configuracionTolerancias.createTitle', 'Nueva tolerancia')
          }
          description={t(
            'configuracionTolerancias.modalDescription',
            'Elegí el alcance (default global o override por sucursal) y cargá las tolerancias.',
          )}
          error={errorState?.message ?? null}
          contentProps={{ 'data-testid': 'tolerancia-form-modal' }}
        >
          {editing !== null ? (
            <ConfiguracionToleranciasForm
              form={undefined as never}
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate
              initialTolerancia={editing}
              onCancel={closeModal}
            />
          ) : (
            <ConfiguracionToleranciasFormHarness
              onSubmit={onSubmit}
              isSubmitting={submitting}
              isUpdate={false}
              initialTolerancia={null}
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
          {t('configuracionTolerancias.loadError', 'No se pudieron cargar las tolerancias.')}
        </p>
      )}

      {isLoading && rows.length === 0 && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('configuracionTolerancias.loading', 'Cargando tolerancias...')}
        </p>
      )}

      <Tabs defaultValue="all" data-testid="tolerancias-tabs">
        <TabsList>
          <TabsTrigger value="all" data-testid="tolerancias-tab-all">
            {t('configuracionTolerancias.tabs.all', 'Global y overrides')}
          </TabsTrigger>
          <TabsTrigger
            value="active"
            data-testid="tolerancias-tab-active"
            disabled={!selectedSucursal}
          >
            {t('configuracionTolerancias.tabs.active', 'Mi sucursal activa')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="all">
          {!isLoading && rows.length === 0 ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="tolerancia-empty"
            >
              {t(
                'configuracionTolerancias.empty',
                'Aún no hay tolerancias configuradas.',
              )}
            </p>
          ) : (
            <div className="flex flex-col gap-4">
              {globalRow !== null && (
                <Card data-testid="tolerancia-card-global">
                  <CardHeader>
                    <CardTitle>
                      {t('configuracionTolerancias.titleGlobal', 'Default global')}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <RowTable
                      row={globalRow}
                      testIdPrefix="tolerancia"
                      onEdit={() => handleEdit(globalRow)}
                    />
                  </CardContent>
                </Card>
              )}

              {overrides.map((row) => (
                <Card
                  key={row.uuid}
                  data-testid={`tolerancia-card-override-${row.uuid_sucursal ?? 'null'}`}
                >
                  <CardHeader>
                    <CardTitle>
                      {t(
                        'configuracionTolerancias.titleOverride',
                        'Override · sucursal {{uuid}}',
                        { uuid: row.uuid_sucursal ?? '—' },
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <RowTable
                      row={row}
                      testIdPrefix="tolerancia"
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
              data-testid="tolerancias-active-empty-selection"
            >
              {t(
                'configuracionTolerancias.tabs.activeEmpty',
                'Elegí una sucursal en el selector del topbar para ver su override.',
              )}
            </p>
          ) : !activeOverride ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="tolerancia-empty-active"
            >
              {t(
                'configuracionTolerancias.tabs.activeNoOverride',
                'Esta sucursal no tiene un override. Creá uno desde "Global y overrides" o usá el botón "Nueva tolerancia".',
              )}
            </p>
          ) : (
            <Card data-testid="tolerancia-card-active">
              <CardHeader>
                <CardTitle>
                  {t(
                    'configuracionTolerancias.titleOverride',
                    'Override · sucursal {{uuid}}',
                    { uuid: activeOverride.uuid_sucursal ?? '—' },
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <RowTable
                  row={activeOverride}
                  testIdPrefix="tolerancia"
                  onEdit={() => handleEdit(activeOverride)}
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </main>
  );
}
