/**
 * `AdminUsuarioSucursalesManager.tsx` — modal that lets an admin
 * manage the branch assignments of a single user (PR3 of the
 * web_admin redesign).
 *
 * Reads from three SWR-shaped sources:
 *   1. `useAdminUsuarioSucursales(usuario.uuid)` — current assignments.
 *   2. `useSWR('/api/v1/empresa/sucursal')` — full directory of branches
 *      to populate the picker with friendly names.
 *   3. `useAdminAuth().sucursalUuids` — limits the picker to branches
 *      the admin is allowed to see (admin-side tenancy).
 *
 * State machine:
 *   - `pendingAddUuid` — set when the user picks a branch from the
 *     <Select>; "Agregar" commits the call.
 *   - `removingUuid` — set when an admin clicks × on a chip; the chip
 *     stays visible (disabled) until the request resolves.
 *
 * Why we keep the modal mounted across requests: callers expect
 * "the modal stayed open while I assigned 3 branches". No flicker.
 */
import { useState } from 'react';
import * as React from 'react';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAdminAuth } from '@parkos/ui-kit/hooks';
import { parkosFetchRaw } from '@/lib/fetch';

import type { AdminUsuarioRead } from '../api/adminUsuarioSchema';
import { useAdminUsuarioSucursales } from '../hooks/useAdminUsuarioSucursales';

export interface AdminUsuarioSucursalesManagerProps {
  user: AdminUsuarioRead | null;
  onClose: () => void;
  onAssign: (usuarioUuid: string, sucursalUuid: string) => Promise<void>;
  onUnassign: (usuarioUuid: string, sucursalUuid: string) => Promise<void>;
}

interface SucursalListItem {
  uuid: string;
  nombre: string | null;
  prefijo_nombre?: string | null;
}

interface SucursalListResponse {
  items: SucursalListItem[];
}

export function AdminUsuarioSucursalesManager({
  user,
  onClose,
  onAssign,
  onUnassign,
}: AdminUsuarioSucursalesManagerProps): JSX.Element | null {
  const { t } = useTranslation();
  const { sucursalUuids } = useAdminAuth();
  const [pendingAdd, setPendingAdd] = useState<string>('');
  const [busy, setBusy] = useState<{ kind: 'add' | 'remove'; uuid: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = user !== null;
  const usuarioUuid = user?.uuid ?? null;

  const { asignaciones, refresh } = useAdminUsuarioSucursales(usuarioUuid);

  const sucursalesDir = useSWR<SucursalListResponse>(
    '/api/v1/empresa/sucursal?limit=200',
    async (key: string) => {
      const res = await parkosFetchRaw(key, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as SucursalListResponse;
    },
    { revalidateOnFocus: false },
  );

  if (!open || user === null) return null;

  const assignedUuids = new Set((asignaciones ?? []).map((a) => a.uuid_sucursal));

  const allowed = (sucursalesDir.data?.items ?? []).filter((s) =>
    sucursalUuids.length === 0 ? true : sucursalUuids.includes(s.uuid),
  );
  const available = allowed.filter((s) => !assignedUuids.has(s.uuid));

  async function handleAdd(): Promise<void> {
    if (!user || pendingAdd === '') return;
    setBusy({ kind: 'add', uuid: pendingAdd });
    setError(null);
    try {
      await onAssign(user.uuid, pendingAdd);
      await refresh();
      setPendingAdd('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'error');
    } finally {
      setBusy(null);
    }
  }

  async function handleRemove(sucursalUuid: string): Promise<void> {
    if (!user) return;
    setBusy({ kind: 'remove', uuid: sucursalUuid });
    setError(null);
    try {
      await onUnassign(user.uuid, sucursalUuid);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'error');
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
      contentProps={
        {
          'data-testid': 'admin-sucursales-modal',
        } as React.HTMLAttributes<HTMLDivElement> & {
          'data-testid'?: string;
        }
      }
    >
      <div className="mx-auto flex max-w-lg flex-col gap-4 rounded-xl border bg-card p-6 shadow-elevation-2">
        <DialogTitle>
          {t('gestionUsuarios.sucursalesManager.title', 'Sucursales del usuario')}
        </DialogTitle>
        <DialogDescription>
          {t(
            'gestionUsuarios.sucursalesManager.subtitle',
            'Asigná o quitá sucursales. Los cambios se aplican al instante.',
          )}
        </DialogDescription>

        <div>
          <p className="text-sm font-medium">
            {user.email ?? user.uuid.slice(0, 8)}
          </p>
          <p className="text-muted-foreground text-xs">
            {([user.nombre, user.apellido].filter(Boolean).join(' ') || user.rol) ?? '—'}
          </p>
        </div>

        {error !== null && (
          <p
            role="alert"
            aria-live="assertive"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            data-testid="admin-sucursales-error"
          >
            {error}
          </p>
        )}

        <div>
          <p className="mb-2 text-sm font-medium">
            {t('gestionUsuarios.sucursalesManager.assigned', 'Asignadas')}
          </p>
          {(asignaciones ?? []).length === 0 ? (
            <p
              className="text-muted-foreground text-xs"
              data-testid="admin-sucursales-empty"
            >
              {t('gestionUsuarios.sucursalesManager.empty', 'Sin sucursales asignadas.')}
            </p>
          ) : (
            <ul className="flex flex-wrap gap-1" aria-label="Sucursales asignadas">
              {(asignaciones ?? []).map((a) => {
                const dirEntry = allowed.find((s) => s.uuid === a.uuid_sucursal);
                const label = dirEntry?.nombre ?? a.uuid_sucursal.slice(0, 8);
                const isBusy =
                  busy?.kind === 'remove' && busy.uuid === a.uuid_sucursal;
                return (
                  <li key={a.uuid_sucursal}>
                    <Badge
                      variant="secondary"
                      className="gap-1"
                      data-testid={`admin-sucursales-chip-${a.uuid_sucursal}`}
                    >
                      <span>{label}</span>
                      <button
                        type="button"
                        onClick={() => void handleRemove(a.uuid_sucursal)}
                        disabled={isBusy}
                        aria-label={`Quitar ${label}`}
                        data-testid={`admin-sucursales-remove-${a.uuid_sucursal}`}
                        className="hover:text-destructive focus-ring rounded-sm"
                      >
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    </Badge>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div>
          <label
            htmlFor="admin-sucursales-add-select"
            className="mb-2 block text-sm font-medium"
          >
            {t('gestionUsuarios.sucursalesManager.addLabel', 'Agregar sucursal')}
          </label>
          <div className="flex gap-2">
            <select
              id="admin-sucursales-add-select"
              data-testid="admin-sucursales-add-select"
              value={pendingAdd}
              onChange={(e) => setPendingAdd(e.target.value)}
              disabled={busy !== null || available.length === 0}
              className="flex h-9 flex-1 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">
                {available.length === 0
                  ? t(
                      'gestionUsuarios.sucursalesManager.noneAvailable',
                      'No hay sucursales disponibles para asignar.',
                    )
                  : t(
                      'gestionUsuarios.sucursalesManager.addPlaceholder',
                      'Elegí una sucursal…',
                    )}
              </option>
              {available.map((s) => (
                <option key={s.uuid} value={s.uuid}>
                  {s.nombre ?? s.uuid}
                </option>
              ))}
            </select>
            <Button
              type="button"
              size="sm"
              disabled={pendingAdd === '' || busy !== null}
              onClick={() => void handleAdd()}
              data-testid="admin-sucursales-add"
            >
              {busy?.kind === 'add' ? t('common.loading', 'Cargando…') : t('gestionUsuarios.sucursalesManager.add', 'Agregar')}
            </Button>
          </div>
        </div>

        <div className="flex items-center justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            data-testid="admin-sucursales-close"
          >
            {t('common.close', 'Cerrar')}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
