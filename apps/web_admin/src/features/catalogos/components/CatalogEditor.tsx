/**
 * `CatalogEditor` — orquestador presentacional por tab.
 *
 * Compone:
 *   - Tabla cruda con versiones vigentes filtradas (HTML `<table>`,
 *     consistente con `SeleccionarSucursal`, `AuditDashboard`, etc.)
 *   - `<NuevaVersionDialog>` para crear o cerrar+insert,
 *   - llamadas a `catalogApi` para POST/PUT y `useCatalogList` para refetch.
 *
 * NO conoce ningún catálogo concreto — todo viene de la `config`.
 * El botón dice "Nueva versión", no "Editar", porque la API nunca
 * hace UPDATE físico (close+insert bi-temporal, REQ-04/05).
 *
 * Errores 403 (sin `config_catalogo`) se renderizan inline con el
 * motivo exacto — el operador ve por qué no puede escribir.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ParkosHttpError } from '@/lib/fetch';

import { NuevaVersionDialog } from './NuevaVersionDialog';
import { VigenteBadge } from './VigenteBadge';
import { useCatalogList } from '../hooks/useCatalogList';
import {
  createCatalogVersion,
  updateCatalogVersion,
  type CatalogRow,
} from '../api/catalogApi';
import type { CatalogConfig } from '../lib/configTypes';

interface CatalogEditorProps {
  config: CatalogConfig;
}

export function CatalogEditor({ config }: CatalogEditorProps): JSX.Element {
  const { t } = useTranslation();
  const { rows, error, isLoading, mutate } = useCatalogList(config.resource);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CatalogRow | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const vigentes = useMemo(
    () => rows.filter((r) => r.vigente_hasta === null && r.estado === 'activo'),
    [rows],
  );

  async function handleSubmit(values: Record<string, unknown>): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      if (editing) {
        await updateCatalogVersion(config.resource, editing.uuid, values);
      } else {
        await createCatalogVersion(config.resource, values);
      }
      await mutate();
      setDialogOpen(false);
      setEditing(null);
    } catch (err) {
      if (err instanceof ParkosHttpError && err.status === 403) {
        setSubmitError(
          t('catalogos.forbidden', 'No tenés permiso para editar este catálogo.'),
        );
      } else {
        setSubmitError(
          t('catalogos.submitError', 'No se pudo guardar. Reintentá.'),
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  function openNew(): void {
    setEditing(null);
    setSubmitError(null);
    setDialogOpen(true);
  }

  function openEdit(row: CatalogRow): void {
    setEditing(row);
    setSubmitError(null);
    setDialogOpen(true);
  }

  const dialogDefaults = editing
    ? Object.fromEntries(
        config.fields.map((f) => [f.name, editing[f.name] ?? '']),
      )
    : config.defaults;

  return (
    <Card data-testid={`catalog-editor-${config.resource}`}>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>{config.pluralLabel}</CardTitle>
        <Button
          type="button"
          onClick={openNew}
          data-testid={`catalog-new-${config.resource}`}
        >
          {t('catalogos.newVersion', 'Nueva versión')}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {error !== undefined && (
          <p
            role="alert"
            aria-live="assertive"
            className="border-destructive/50 bg-destructive/10 text-destructive rounded-md border px-3 py-2 text-sm"
            data-testid={`catalog-error-${config.resource}`}
          >
            {t('catalogos.loadError', 'No se pudo cargar el catálogo.')}
          </p>
        )}

        {isLoading && rows.length === 0 ? (
          <p
            role="status"
            aria-live="polite"
            className="text-muted-foreground text-sm"
          >
            {t('catalogos.loading', 'Cargando…')}
          </p>
        ) : vigentes.length === 0 ? (
          <p
            className="text-muted-foreground text-sm"
            data-testid={`catalog-empty-${config.resource}`}
          >
            {t('catalogos.empty', 'Sin versiones vigentes.')}
          </p>
        ) : (
          <div
            className="overflow-x-auto rounded-lg border bg-card"
            data-testid={`catalog-table-${config.resource}`}
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left">
                  <th className="px-3 py-2" scope="col">
                    {t('catalogos.estado', 'Estado')}
                  </th>
                  {config.columns.map((c) => (
                    <th key={c.key} className="px-3 py-2" scope="col">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {vigentes.map((row) => (
                  <tr
                    key={row.uuid}
                    data-testid={`catalog-row-${row.uuid}`}
                    className="cursor-pointer border-b hover:bg-accent/40"
                    role="button"
                    tabIndex={0}
                    aria-label={t(
                      'catalogos.editRowAria',
                      'Nueva versión basada en la fila {{uuid}}',
                      { uuid: row.uuid },
                    )}
                    onClick={() => openEdit(row)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        openEdit(row);
                      }
                    }}
                  >
                    <td className="px-3 py-2">
                      <VigenteBadge
                        vigenteHasta={row.vigente_hasta}
                        estado={row.estado}
                      />
                    </td>
                    {config.columns.map((c) => (
                      <td key={c.key} className="px-3 py-2">
                        {c.render
                          ? c.render(row[c.key], row)
                          : String(row[c.key] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <NuevaVersionDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t('catalogos.dialogTitle', 'Nueva versión')}
        description={t(
          'catalogos.dialogDescription',
          'Creá una nueva versión. La actual se cierra automáticamente al guardar.',
        )}
        fields={config.fields}
        defaults={dialogDefaults}
        onSubmit={handleSubmit}
        isSubmitting={submitting}
      />

      {submitError !== null && (
        <p
          role="alert"
          aria-live="assertive"
          className="text-destructive mt-2 px-6 text-xs"
          data-testid={`catalog-submit-error-${config.resource}`}
        >
          {submitError}
        </p>
      )}
    </Card>
  );
}
