/**
 * `<SucursalesList />` -- container that lists admin's permitted
 * branches and exposes the "Nueva sucursal" + "Pairing token" actions
 * (IT-2.1, IT-2.7).
 *
 * Container/presentational split (mirror of Login page):
 * - This file owns state, data fetching, and the open/close lifecycle
 *   of the SucursalForm modal + PairingTokenDialog.
 * - SucursalForm + PairingTokenDialog are presentational.
 *
 * Data flow:
 *   1. On mount, SWR fetches `GET /api/v1/empresa/sucursal` (admin or
 *      operador allowed by `sucursal` config in `_ROUTER_CONFIG`).
 *   2. "Nueva sucursal" opens the SucursalForm modal; submit calls
 *      `createSucursal` (POST) and triggers an SWR revalidation.
 *   3. The "Pairing token" button per row opens the PairingTokenDialog;
 *      on open it calls `mintPairingToken(sucursalUuid)` (GET) and
 *      displays the returned token + countdown.
 */
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import useSWR from 'swr';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { SucursalForm } from '../components/SucursalForm';
import { PairingTokenDialog } from '../components/PairingTokenDialog';
import { createSucursal, listSucursales, mintPairingToken } from '../api/sucursalesApi';
import {
  sucursalCreateSchema,
  type PairingTokenResponse,
  type SucursalCreateInput,
  type Sucursal,
} from '../api/sucursalSchema';

const LIST_KEY = '/api/v1/empresa/sucursal';

interface CreateSucursalError {
  kind: 'validation' | 'server' | 'network';
  message: string;
}

export default function SucursalesList() {
  const { t } = useTranslation();
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState<CreateSucursalError | null>(null);
  const [pairingToken, setPairingToken] = useState<PairingTokenResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const {
    data: sucursales,
    mutate,
    error,
    isLoading,
  } = useSWR<Sucursal[]>(LIST_KEY, () => listSucursales({ limit: 100 }), {
    revalidateOnFocus: false,
  });

  const createForm = useForm<SucursalCreateInput>({
    resolver: zodResolver(sucursalCreateSchema),
    defaultValues: {
      nombre: '',
      prefijo_nombre: '',
      ciudad: '',
      telefono: '',
      direccion: '',
    },
  });

  async function onCreateSubmit(values: SucursalCreateInput) {
    setIsCreating(true);
    setCreateError(null);
    try {
      await createSucursal(values);
      setShowCreate(false);
      createForm.reset();
      await mutate();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'unknown error';
      setCreateError({ kind: 'network', message });
    } finally {
      setIsCreating(false);
    }
  }

  async function onPairingClick(sucursalUuid: string) {
    try {
      const token = await mintPairingToken(sucursalUuid);
      setPairingToken(token);
    } catch (err) {
      // The dialog stays closed; a minimal inline error is enough for
      // IT-2.7 -- a richer toast/error surface lands in a follow-up.
      const message = err instanceof Error ? err.message : 'unknown error';
      setCreateError({ kind: 'server', message });
    }
  }

  return (
    <main
      className="flex min-h-screen flex-col gap-4 bg-background p-4"
      data-testid="page-sucursales"
    >
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('sucursal.title')}</h1>
        <Button type="button" onClick={() => setShowCreate(true)} data-testid="sucursal-new">
          {t('sucursal.new')}
        </Button>
      </header>

      {showCreate && (
        <Card data-testid="sucursal-create-card">
          <CardHeader>
            <CardTitle>{t('sucursal.createTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            {createError !== null && (
              <p
                role="alert"
                aria-live="assertive"
                data-testid="sucursal-create-error"
                className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {createError.message}
              </p>
            )}
            <SucursalForm form={createForm} onSubmit={onCreateSubmit} isSubmitting={isCreating} />
            <Button
              type="button"
              variant="ghost"
              className="mt-2 w-full"
              onClick={() => {
                setShowCreate(false);
                createForm.reset();
                setCreateError(null);
              }}
              data-testid="sucursal-create-cancel"
            >
              {t('common.cancel')}
            </Button>
          </CardContent>
        </Card>
      )}

      {error !== undefined && (
        <p
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {t('sucursal.loadError')}
        </p>
      )}

      {isLoading && sucursales === undefined && (
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {t('sucursal.loading')}
        </p>
      )}

      {sucursales !== undefined && (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="px-3 py-2">{t('sucursal.col.nombre')}</th>
                <th className="px-3 py-2">{t('sucursal.col.prefijo')}</th>
                <th className="px-3 py-2">{t('sucursal.col.ciudad')}</th>
                <th className="px-3 py-2 text-right">{t('sucursal.col.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {sucursales.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-6 text-center text-muted-foreground">
                    {t('sucursal.empty')}
                  </td>
                </tr>
              )}
              {sucursales.map((s) => (
                <tr key={s.uuid} className="border-b">
                  <td className="px-3 py-2 font-medium">{s.nombre ?? s.uuid}</td>
                  <td className="px-3 py-2 font-mono text-xs">{s.prefijo_nombre ?? '—'}</td>
                  <td className="px-3 py-2">{s.ciudad ?? '—'}</td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => void onPairingClick(s.uuid)}
                      data-testid={`sucursal-pairing-${s.uuid}`}
                    >
                      {t('sucursal.action.pairing')}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <PairingTokenDialog token={pairingToken} onClose={() => setPairingToken(null)} />
    </main>
  );
}
