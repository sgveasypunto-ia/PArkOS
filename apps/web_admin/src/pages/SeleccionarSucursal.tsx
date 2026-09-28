/**
 * SeleccionarSucursal — gate page shown after login and when the operator
 * clicks the chrome badge to switch.
 *
 * The admin may have many branches in their JWT claim
 * (`sucursales_permitidas`); we cross-reference that list against the
 * full `/api/v1/empresa/sucursal` list to get names. Branches in the
 * claim that do not yet have a name in the directory (race during
 * provisioning) still appear with their UUID as label — we never
 * silently hide a branch the operator is allowed to see.
 *
 * On select:
 *   1. Persist via `useSucursal().setSelected(uuid)` (which writes
 *      `localStorage['parkos.lastSelectedSucursal']`).
 *   2. Navigate to `/dashboard` with `replace: true` so the picker is
 *      not in the back stack.
 *
 * WHY THIS PAGE IS NOT WRAPPED BY `RequireSucursal`:
 *   `RequireSucursal` redirects to `/seleccionar-sucursal` when no
 *   branch is selected. Putting this route INSIDE that guard would loop
 *   forever. It sits at the top level of the route tree, gated only by
 *   `RequireAdmin` (auth), never by `RequireSucursal`.
 */
import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { parkosFetchRaw } from '@/lib/fetch';
import { useSucursal } from '@/lib/sucursal-context';

import { SucursalPicker, type SucursalPickerOption } from '@/components/branch-selector/SucursalPicker';

interface SucursalListResponse {
  items: SucursalPickerOption[];
}

export default function SeleccionarSucursal(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { sucursalUuids, isLoading: isAdminLoading } = useAdminAuth();
  const { selected, setSelected } = useSucursal();

  const list = useSWR<SucursalListResponse>(
    '/api/v1/empresa/sucursal',
    async (key: string) => {
      const res = await parkosFetchRaw(key, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as SucursalListResponse;
    },
    { revalidateOnFocus: false },
  );

  const allowed = useMemo<SucursalPickerOption[]>(() => {
    const items = list.data?.items ?? [];
    if (sucursalUuids.length === 0) return items;
    const set = new Set(sucursalUuids);
    return items.filter((i) => set.has(i.uuid));
  }, [list.data, sucursalUuids]);

  useEffect(() => {
    if (
      selected &&
      sucursalUuids.length > 0 &&
      !sucursalUuids.includes(selected)
    ) {
      setSelected(null);
    }
  }, [selected, sucursalUuids, setSelected]);

  const handleSelect = (uuid: string): void => {
    setSelected(uuid);
    navigate('/dashboard', { replace: true });
  };

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
    <SucursalPicker
      options={allowed}
      isLoading={list.isLoading}
      onSelect={handleSelect}
    />
  );
}
