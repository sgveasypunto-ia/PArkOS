/**
 * SeleccionarSucursal -- unified page that combines the branch picker
 * (cards, post-login gate / chrome badge target) with branch CRUD
 * management (create, edit, pairing token mint).
 *
 * Replaces the previous two-page split: `/seleccionar-sucursal`
 * (picker only) + `/sucursales` (CRUD only). The chrome badge still
 * navigates here; the unified surface handles both flows.
 *
 * Two tabs, default "Seleccionar":
 *   - Tab "Seleccionar": cards via <SucursalPicker>. Click a card ->
 *     `useSucursal().setSelected(uuid)` + navigate /dashboard.
 *   - Tab "Administrar": table with Edit + Pairing actions + "Nueva
 *     sucursal" button. Endpoints: `/api/v1/empresa/sucursal` (factory,
 *     full bi-temporal shape needed for edit).
 *
 * `?tab=admin` query param auto-switches to the Administrar tab so the
 * legacy `/sucursales` redirect (Navigate to /seleccionar-sucursal?tab=admin)
 * lands in the right view.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { parkosFetchRaw } from '@/lib/fetch';
import { useSucursal } from '@/lib/sucursal-context';
import { PageHeader } from '@/components/layout/PageHeader';
import {
  SucursalPicker,
  type SucursalPickerOption,
} from '@/components/branch-selector/SucursalPicker';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';

import { BaseCajaEditor } from '@/features/configuracion-caja/components/BaseCajaEditor';
import { useBasesCajaSucursales } from '@/features/configuracion-caja/hooks/useBasesCajaSucursales';
import { SucursalFormHarness } from '@/features/sucursales/components/SucursalForm';
import { useTipoSucursal } from '@/features/tipo-sucursal/hooks/useTipoSucursal';
import {
  createSucursal,
  updateSucursal,
} from '@/features/sucursales/api/sucursalesApi';
import { useSucursalesDirectorio } from '@/features/sucursales/hooks/useSucursalesDirectorio';
import {
  type Sucursal,
  type SucursalCreateInput,
} from '@/features/sucursales/api/sucursalSchema';

type TabValue = 'seleccionar' | 'admin';

type ErrorState =
  | { kind: 'create' | 'edit' | 'load'; message: string }
  | null;

function mapTab(value: string | null): TabValue {
  return value === 'admin' ? 'admin' : 'seleccionar';
}

export default function SeleccionarSucursal(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { sucursalUuids, isLoading: isAdminLoading, refresh: refreshAdminAuth } = useAdminAuth();
  const { selected, setSelected } = useSucursal();

  const tab = mapTab(searchParams.get('tab'));

  function setTab(next: TabValue): void {
    const params = new URLSearchParams(searchParams);
    if (next === 'seleccionar') {
      params.delete('tab');
    } else {
      params.set('tab', next);
    }
    setSearchParams(params, { replace: true });
  }

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------
  // Picker: admin_views endpoint (lighter, scoped to permitted branches).
  const listForPicker = useSWR<Array<{ uuid: string; nombre: string | null }>>(
    '/api/v1/sucursales',
    async (key: string) => {
      const res = await parkosFetchRaw(key, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = (await res.json()) as unknown;
      if (!body || typeof body !== 'object' || !('items' in body)) {
        throw new Error('Invalid response shape: missing items');
      }
      const items = (body as { items: unknown }).items;
      if (!Array.isArray(items)) {
        throw new Error('Invalid response shape: items is not an array');
      }
      return items as Array<{ uuid: string; nombre: string | null }>;
    },
    { revalidateOnFocus: false },
  );

  // Admin table: factory endpoint (full bi-temporal shape needed for edit).
  const listForAdmin = useSucursalesDirectorio();
  // Base de caja por sucursal (override) + default global, en una sola consulta.
  const basesCaja = useBasesCajaSucursales();

  // -------------------------------------------------------------------------
  // Picker derived state
  // -------------------------------------------------------------------------
  const allowedPickerOptions = useMemo<SucursalPickerOption[]>(() => {
    const rawItems = listForPicker.data;
    const items = Array.isArray(rawItems) ? rawItems : [];
    if (sucursalUuids.length === 0) return items;
    const set = new Set(sucursalUuids);
    return items
      .filter((i) => set.has(i.uuid))
      .map((i) => ({ uuid: i.uuid, nombre: i.nombre, prefijo_nombre: null }));
  }, [listForPicker.data, sucursalUuids]);

  useEffect(() => {
    if (selected && sucursalUuids.length > 0 && !sucursalUuids.includes(selected)) {
      setSelected(null);
    }
  }, [selected, sucursalUuids, setSelected]);

  // -------------------------------------------------------------------------
  // Admin CRUD state
  // -------------------------------------------------------------------------
  // Catalog for FK auto-fill on create: `uuid_tipo_sucursal` defaults
  // to the first tipo_sucursal UUID (mirror of `bootstrap_pairing.py`
  // pattern). The field is rendered `readOnly` regardless, so the
  // operator cannot change it from the form.
  const { tipos: tiposSucursal } = useTipoSucursal();
  const defaultTipoSucursalUuid = tiposSucursal[0]?.uuid ?? null;

  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Sucursal | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<ErrorState>(null);
  // Free-text filter over the admin table. State is kept at the page
  // level (NOT the TabsContent level) so it survives tab switches --
  // the user's expectation: type a query, switch to "Seleccionar",
  // switch back, the query is still there. Empty string = no filter.
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Accent- and case-insensitive match: "bogota", "Bogotá", "BOGOTÁ"
  // all hit a row with ciudad "Bogotá". The same NFD-stripped query is
  // compared against the three searchable fields (nombre,
  // prefijo_nombre, ciudad); a row matches if ANY field contains the
  // query as a substring. Null fields are treated as "no match" so
  // "null" never appears in the search results.
  const filteredSucursales = useMemo<Sucursal[]>(() => {
    const base = listForAdmin.sucursales;
    const normalizedQuery = searchQuery
      .trim()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
    if (normalizedQuery === '') return base;
    return base.filter((s) => {
      const candidates = [s.nombre, s.prefijo_nombre, s.ciudad];
      return candidates.some((value) => {
        if (value === null || value === undefined) return false;
        return value
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .toLowerCase()
          .includes(normalizedQuery);
      });
    });
  }, [listForAdmin.sucursales, searchQuery]);

  function closeModal(): void {
    setShowCreate(false);
    setEditing(null);
    setErrorState(null);
  }

  async function onSubmit(values: SucursalCreateInput): Promise<void> {
    setSubmitting(true);
    setErrorState(null);
    try {
      if (editing !== null) {
        await updateSucursal(editing.uuid, values);
      } else {
        await createSucursal(values);
      }
      closeModal();
      // Refresh SWR caches that the mutation invalidated:
      //  - ``listForPicker`` + ``listForAdmin``: re-fetch the branch list
      //    (server-side fix already returns the new branch from
      //    ``/api/v1/sucursales``; this clears the local SWR cache).
      //  - ``refreshAdminAuth``: re-fetch ``/api/v1/admin/me`` so the
      //    cached ``sucursalUuids`` JWT-claim-derived list picks up the
      //    new branch. Without this, the picker filter (line 124)
      //    excludes the just-created branch until ``REFRESH_INTERVAL_MS``
      //    (50 min) elapses or the admin re-logs. See commit history for
      //    the full trace -- the user's "must re-login" report 2026-09-29.
      await Promise.all([
        listForPicker.mutate?.(),
        listForAdmin.refresh(),
        refreshAdminAuth(),
      ]);
    } catch (err) {
      let message = err instanceof Error ? err.message : 'Error desconocido';
      // 409 `sucursal_prefijo_duplicado` (empresa.py's sucursal dedicated
      // router) — `sucursalesApi.ts`'s `fetchJson` throws a plain `Error`
      // whose `.message` embeds the raw response body, same shape as
      // `tiposVehiculoApi.ts`; extract the typed code for a readable copy.
      const bodyStart = message.indexOf('{');
      if (bodyStart !== -1) {
        try {
          const parsed = JSON.parse(message.slice(bodyStart)) as {
            detail?: { error?: string };
          };
          if (parsed.detail?.error === 'sucursal_prefijo_duplicado') {
            message = 'Ya existe una sucursal vigente con ese mismo prefijo.';
          }
        } catch {
          // Not JSON (or unknown shape) — keep the raw message.
        }
      }
      setErrorState({ kind: editing !== null ? 'edit' : 'create', message });
    } finally {
      setSubmitting(false);
    }
  }

  function handleSelect(uuid: string): void {
    setSelected(uuid);
    navigate('/dashboard', { replace: true });
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  if (isAdminLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="text-muted-foreground flex min-h-screen items-center justify-center text-sm"
        data-testid="seleccionar-sucursal-loading"
      >
        {t('sucursalPicker.loading', 'Cargando sucursales…')}
      </div>
    );
  }

  return (
    <main
      className="flex flex-1 flex-col gap-6 bg-background p-4 md:p-6 lg:p-8"
      data-testid="page-seleccionar-sucursal"
    >
      <Tabs
        value={tab}
        onValueChange={(v) => setTab(mapTab(v))}
        data-testid="sucursal-unified-tabs"
      >
        <TabsList>
          <TabsTrigger value="seleccionar" data-testid="sucursal-tab-seleccionar">
            {t('sucursalAdmin.tab.seleccionar', 'Seleccionar')}
          </TabsTrigger>
          <TabsTrigger value="admin" data-testid="sucursal-tab-admin">
            {t('sucursalAdmin.tab.admin', 'Administrar')}
          </TabsTrigger>
        </TabsList>

        {/* =================================================================
            Tab: Seleccionar (cards)
           ================================================================= */}
        <TabsContent value="seleccionar">
          <SucursalPicker
            options={allowedPickerOptions}
            isLoading={listForPicker.isLoading}
            onSelect={handleSelect}
          />
        </TabsContent>

        {/* =================================================================
            Tab: Administrar (table + CRUD)
           ================================================================= */}
        <TabsContent value="admin">
          <PageHeader
            className="mb-2"
            title={t('sucursalAdmin.title.admin', 'Sucursales')}
            actions={
              <Button
                type="button"
                onClick={() => {
                  setShowCreate(true);
                  setEditing(null);
                  setErrorState(null);
                }}
                data-testid="sucursal-new"
              >
                {t('sucursal.new', 'Nueva sucursal')}
              </Button>
            }
          />

          {/* Free-text filter. Single input matches against nombre,
              prefijo_nombre, AND ciudad (accent/case-insensitive). The
              `htmlFor`/`id` pair wires the input to its visible label
              so axe-core sees an accessible form field (the X button
              below carries its own aria-label so the search row still
              has a single labeled control). */}
          <div className="mb-4 flex items-center gap-2">
            <label
              htmlFor="sucursal-search-input"
              className="sr-only"
            >
              {t(
                'sucursalAdmin.search.placeholder',
                'Buscar por nombre, prefijo o ciudad…',
              )}
            </label>
            <Input
              id="sucursal-search-input"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t(
                'sucursalAdmin.search.placeholder',
                'Buscar por nombre, prefijo o ciudad…',
              )}
              className="max-w-sm"
              data-testid="sucursal-search"
              autoComplete="off"
              spellCheck={false}
            />
            {searchQuery !== '' && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSearchQuery('')}
                aria-label={t(
                  'sucursalAdmin.search.clearAria',
                  'Limpiar búsqueda',
                )}
                data-testid="sucursal-search-clear"
              >
                ✕
              </Button>
            )}
          </div>

          {(showCreate || editing !== null) && (
            <Card className="mb-4" data-testid="sucursal-form-card">
              <CardHeader>
                <CardTitle>
                  {editing !== null
                    ? t('sucursal.editTitle', 'Editar sucursal')
                    : t('sucursal.createTitle', 'Nueva sucursal')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {errorState !== null && (
                  <p
                    role="alert"
                    aria-live="assertive"
                    data-testid="sucursal-form-error"
                    className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                  >
                    {errorState.message}
                  </p>
                )}
                <SucursalFormHarness
                  onSubmit={onSubmit}
                  isSubmitting={submitting}
                  isUpdate={editing !== null}
                  initialSucursal={editing}
                  onCancel={closeModal}
                  defaultTipoSucursalUuid={defaultTipoSucursalUuid}
                />
              </CardContent>
            </Card>
          )}

          {/* Base de caja: cada sucursal puede tener más o menos base. La
              propia de la fila gana; la sucursal sin base propia hereda esta
              por defecto. */}
          <Card className="mb-4" data-testid="base-caja-global-card">
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">
                  {t('baseCaja.global.titulo', 'Base de caja por defecto')}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t(
                    'baseCaja.global.ayuda',
                    'La reciben las sucursales que no tienen una base propia. Cada sucursal puede tener la suya en la tabla.',
                  )}
                </p>
              </div>
              <BaseCajaEditor
                testId="base-caja-global"
                base={basesCaja.baseGlobal}
                origen={basesCaja.baseGlobal === null ? 'sin_configurar' : 'propia'}
                onGuardar={(valor) => basesCaja.guardar(null, valor)}
              />
            </CardContent>
          </Card>

          {basesCaja.error !== undefined && (
            <p
              role="alert"
              className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="base-caja-error-carga"
            >
              {t('baseCaja.errorCarga', 'No se pudieron cargar las bases de caja.')}
            </p>
          )}

          {listForAdmin.error !== undefined && (
            <p
              role="alert"
              aria-live="assertive"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {t('sucursal.loadError', 'No se pudieron cargar las sucursales.')}
            </p>
          )}

          {listForAdmin.isLoading && listForAdmin.sucursales.length === 0 && (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
            >
              {t('sucursal.loading', 'Cargando sucursales...')}
            </p>
          )}

          {listForAdmin.sucursales.length === 0 &&
          !listForAdmin.isLoading &&
          listForAdmin.error === undefined ? (
            <p
              role="status"
              aria-live="polite"
              className="text-sm text-muted-foreground"
              data-testid="sucursal-empty"
            >
              {t('sucursal.empty', 'Aún no hay sucursales configuradas.')}
            </p>
          ) : filteredSucursales.length === 0 ? (
            // Base list is non-empty (the branch above handles the
            // truly-empty case) but the filter eliminated every row.
            // Distinct empty state so the admin can tell "no
            // branches" from "no matches for my query".
            <div
              className="flex flex-col items-start gap-2 rounded-lg border bg-card p-4 text-sm"
              data-testid="sucursal-search-no-results"
            >
              <p className="text-muted-foreground">
                {t(
                  'sucursalAdmin.search.noResults',
                  'No se encontraron sucursales que coincidan con "{{query}}".',
                ).replace('{{query}}', searchQuery)}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setSearchQuery('')}
                data-testid="sucursal-search-no-results-clear"
              >
                {t('sucursalAdmin.search.clearAria', 'Limpiar búsqueda')}
              </Button>
            </div>
          ) : (
            <div
              className="overflow-x-auto rounded-lg border bg-card"
              data-testid="sucursal-table-wrapper"
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-3 py-2">
                      {t('sucursal.col.nombre', 'Nombre')}
                    </th>
                    <th className="px-3 py-2">
                      {t('sucursal.col.prefijo', 'Prefijo')}
                    </th>
                    <th className="px-3 py-2">
                      {t('sucursal.col.ciudad', 'Ciudad')}
                    </th>
                    <th className="px-3 py-2">
                      {t('sucursal.col.baseCaja', 'Base de caja por turno')}
                    </th>
                    <th className="px-3 py-2 text-right">
                      {t('sucursal.col.actions', 'Acciones')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSucursales.map((s) => (
                    <tr
                      key={s.uuid}
                      data-testid={`sucursal-row-${s.uuid}`}
                      className="border-b"
                    >
                      <td className="px-3 py-2 font-medium">
                        {s.nombre ?? s.uuid}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {s.prefijo_nombre ?? '—'}
                      </td>
                      <td className="px-3 py-2">{s.ciudad ?? '—'}</td>
                      <td className="px-3 py-2">
                        <BaseCajaEditor
                          testId={`sucursal-base-${s.uuid}`}
                          base={basesCaja.baseDe(s.uuid).base}
                          origen={basesCaja.baseDe(s.uuid).origen}
                          onGuardar={(valor) => basesCaja.guardar(s.uuid, valor)}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setEditing(s);
                              setShowCreate(false);
                              setErrorState(null);
                            }}
                            data-testid={`sucursal-edit-${s.uuid}`}
                          >
                            {t('sucursal.action.edit', 'Editar')}
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate(`/pairing?sucursal=${s.uuid}`)}
                            data-testid={`sucursal-pairing-${s.uuid}`}
                          >
                            {t('sucursal.action.pairing', 'Token de pairing')}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </main>
  );
}
