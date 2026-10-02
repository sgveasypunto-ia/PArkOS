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
      const message = err instanceof Error ? err.message : 'Error desconocido';
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
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
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
          <header className="mb-4 flex items-center justify-between">
            <h1 className="text-2xl font-semibold">
              {t('sucursalAdmin.title.admin', 'Sucursales')}
            </h1>
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
          </header>

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
                    <th className="px-3 py-2 text-right">
                      {t('sucursal.col.actions', 'Acciones')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {listForAdmin.sucursales.map((s) => (
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
