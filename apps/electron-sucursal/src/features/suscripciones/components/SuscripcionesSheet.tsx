/**
 * `<SuscripcionesSheet />` — HU-F9.1 (venta) + HU-F9.2 realineada
 * (listado + búsqueda + cupos) side drawer for the operator.
 *
 * Three-mode drawer, all inside the SAME `<Sheet>` — no route changes,
 * no nested dialogs (operator directive, 2026-09-24):
 *   - `mode='list'` (default) — active branch subscriptions + a
 *     search-by-`numero_identificacion` field. Selecting a result (by
 *     clicking a row or submitting the search) fetches the full detail
 *     and advances to `mode='cupos'`. The "+ Nueva venta" CTA still
 *     switches to `mode='venta'` (HU-F9.1, unchanged).
 *   - `mode='venta'` — the existing 4-step `<Venta />` wizard (F9.1).
 *   - `mode='cupos'` — cupo detail for ONE subscription: plan +
 *     cupo máximo/disponible, the list of enrolled vehicles (each with
 *     a "Quitar" action) and an "agregar vehículo" form gated on
 *     cupo disponible > 0.
 *
 * Mounted via `<DrawerHost>` when
 * `useDashboardDrawerStore.openDrawer === 'suscripciones'` (single-
 * drawer invariant, REQ-OPS-138). Focus restores to the sidebar
 * anchor on close. Resets to `mode='list'` on every open — a stale
 * `'venta'`/`'cupos'` state must never survive across show/hide cycles.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import { useAuth } from '@parkos/ui-kit/hooks';

import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import type { SubscripcionCupoDetalle } from '../api/cuposApi';
import { useAgregarVehiculoSuscripcion } from '../hooks/useAgregarVehiculoSuscripcion';
import { useBuscarSuscripcionPorIdentificacion } from '../hooks/useBuscarSuscripcionPorIdentificacion';
import { useQuitarVehiculoSuscripcion } from '../hooks/useQuitarVehiculoSuscripcion';
import { useSuscripcionesActivas } from '../hooks/useSuscripcionesActivas';
import { Venta } from '../pages/Venta';

type SheetMode = 'list' | 'venta' | 'cupos';

export function SuscripcionesSheet(): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const { sucursal } = useAuth();
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const lastAnchorId = useDashboardDrawerStore((s) => s.lastAnchorId);
  const close = useDashboardDrawerStore((s) => s.close);
  const uuid_sucursal = sucursal?.uuid ?? null;
  const { data, error, refresh } = useSuscripcionesActivas(uuid_sucursal);

  const open = openDrawer === 'suscripciones';

  const [mode, setMode] = useState<SheetMode>('list');
  const [numeroIdentificacion, setNumeroIdentificacion] = useState('');
  const [detalle, setDetalle] = useState<SubscripcionCupoDetalle | null>(null);
  const [nuevaPlaca, setNuevaPlaca] = useState('');

  const buscar = useBuscarSuscripcionPorIdentificacion();
  const agregar = useAgregarVehiculoSuscripcion();
  const quitar = useQuitarVehiculoSuscripcion();

  // Reset to list whenever the drawer opens -- otherwise a stale
  // 'venta'/'cupos' state from a previous session survives across
  // show/hide cycles. Keeps the entry-point behavior predictable.
  useEffect(() => {
    if (open) {
      setMode('list');
      setNumeroIdentificacion('');
      setDetalle(null);
      setNuevaPlaca('');
    }
  }, [open]);

  // REQ-OPS-138 §Esc -- restore DOM focus to the sidebar anchor
  // (data-testid="sidebar-suscripciones") so keyboard users land
  // back on the trigger.
  useEffect(() => {
    if (!open && lastAnchorId) {
      document.getElementById(lastAnchorId)?.focus();
    }
  }, [open, lastAnchorId]);

  const handleNuevaVenta = (): void => {
    setMode('venta');
  };
  const handleVolver = (): void => {
    setMode('list');
    setDetalle(null);
  };
  const handleVentaSuccess = (): void => {
    void refresh();
    close();
  };

  // Every `trigger(...)` call below is wrapped in try/catch: SWR mutation
  // hooks reject the returned promise on error (that's how `.error`
  // gets populated for the inline alert), so an un-caught `await` here
  // surfaces as an "Uncaught (in promise)" console error on every 4xx/5xx
  // (real bug found live 2026-09-24 triggering a 409 vehiculo_ya_inscrito
  // from the UI) even though the error message already renders correctly
  // via `agregar.error`/`quitar.error`/`buscar.error`. The catch blocks
  // are intentionally empty — the reactive `.error` state is the single
  // source of truth for what the operator sees.

  const handleBuscar = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    const trimmed = numeroIdentificacion.trim();
    if (!trimmed) return;
    try {
      const found = await buscar.trigger(trimmed);
      if (found) {
        setDetalle(found);
        setMode('cupos');
      }
    } catch {
      // buscar.error already carries the message for the alert.
    }
  };

  const handleVerCupos = (item: { cliente: { numero_identificacion: string | null } }): void => {
    const numero = item.cliente.numero_identificacion;
    if (!numero) return;
    setNumeroIdentificacion(numero);
    buscar
      .trigger(numero)
      .then((found) => {
        if (found) {
          setDetalle(found);
          setMode('cupos');
        }
      })
      .catch(() => {
        // buscar.error already carries the message for the alert.
      });
  };

  const handleAgregar = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    if (!detalle) return;
    const placa = nuevaPlaca.trim();
    if (!placa) return;
    try {
      const actualizado = await agregar.trigger({
        uuid_subscripcion_cliente: detalle.uuid,
        placa,
      });
      setDetalle(actualizado);
      setNuevaPlaca('');
      void refresh();
    } catch {
      // agregar.error already carries the message for the alert.
    }
  };

  const handleQuitar = async (uuidSubscripcionVehiculo: string): Promise<void> => {
    try {
      const actualizado = await quitar.trigger(uuidSubscripcionVehiculo);
      setDetalle(actualizado);
      void refresh();
    } catch {
      // quitar.error already carries the message for the alert.
    }
  };

  const cupoLleno = detalle?.cupo_disponible !== null && (detalle?.cupo_disponible ?? 0) <= 0;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="right"
        data-testid="suscripciones-sheet"
        className="flex h-full w-[70vw] max-w-[1100px] flex-col gap-6"
      >
        <SheetHeader className="pr-8">
          <SheetTitle>
            {mode === 'venta' &&
              t('suscripciones:sheet.tituloVenta', {
                defaultValue: 'Nueva venta de suscripción',
              })}
            {mode === 'cupos' &&
              t('suscripciones:sheet.tituloCupos', { defaultValue: 'Gestión de cupos' })}
            {mode === 'list' &&
              t('suscripciones:sheet.titulo', { defaultValue: 'Suscripciones' })}
          </SheetTitle>
          <SheetDescription>
            {mode === 'list' &&
              t('suscripciones:sheet.descripcion', {
                defaultValue: 'Lista activa de suscripciones en esta sede.',
              })}
            {mode === 'venta' &&
              t('suscripciones:sheet.descripcionVenta', {
                defaultValue:
                  'Venta de suscripción en 4 pasos. Al pagar, regresa a esta pestaña.',
              })}
            {mode === 'cupos' &&
              t('suscripciones:sheet.descripcionCupos', {
                defaultValue: 'Agregá o quitá vehículos inscritos en esta suscripción.',
              })}
          </SheetDescription>
        </SheetHeader>

        {/* Body scrolls independently of header + footer. */}
        <div
          className="flex-1 overflow-y-auto px-4"
          data-testid="suscripciones-sheet-body"
        >
          {mode === 'list' && (
            <div className="space-y-4">
              <form
                className="mt-[10px] flex gap-2"
                onSubmit={(e) => void handleBuscar(e)}
                data-testid="suscripciones-buscar-form"
              >
                <Input
                  id="suscripciones-buscar-input"
                  name="numero_identificacion"
                  value={numeroIdentificacion}
                  onChange={(e) => setNumeroIdentificacion(e.target.value)}
                  placeholder={t('suscripciones:sheet.buscarPlaceholder', {
                    defaultValue: 'Número de identificación',
                  })}
                  data-testid="suscripciones-buscar-input"
                  aria-label={t('suscripciones:sheet.buscarPlaceholder', {
                    defaultValue: 'Número de identificación',
                  })}
                />
                <Button
                  type="submit"
                  variant="secondary"
                  disabled={buscar.isMutating}
                  data-testid="suscripciones-buscar-submit"
                >
                  {t('suscripciones:sheet.buscar', { defaultValue: 'Buscar' })}
                </Button>
              </form>
              {buscar.data === null && (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="suscripciones-buscar-sin-resultado"
                >
                  {t('suscripciones:sheet.buscarSinResultado', {
                    defaultValue: 'No hay una suscripción activa con ese número.',
                  })}
                </p>
              )}

              {error && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                  data-testid="suscripciones-sheet-error"
                >
                  {t('suscripciones:error', {
                    defaultValue: 'Error al cargar suscripciones.',
                  })}
                </p>
              )}
              {data && data.length === 0 && (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="suscripciones-sheet-empty"
                >
                  {t('suscripciones:sheet.listaVacia', {
                    defaultValue: 'Sin suscripciones activas en esta sede.',
                  })}
                </p>
              )}
              {data && data.length > 0 && (
                <ul className="space-y-2" data-testid="suscripciones-sheet-list">
                  {data.map((s) => (
                    <li key={s.uuid}>
                      <button
                        type="button"
                        onClick={() => handleVerCupos(s)}
                        data-testid={`suscripciones-sheet-item-${s.uuid}`}
                        className="w-full rounded border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">
                            {s.cliente.nombre} {s.cliente.apellido}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {s.plan.tipo}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            {t('suscripciones:sheet.vence', { defaultValue: 'Vence' })}:{' '}
                            {s.fecha_vencimiento}
                          </span>
                          <span data-testid={`suscripciones-sheet-cupo-${s.uuid}`}>
                            {s.vehiculos_inscritos}/{s.cupo_maximo ?? '—'}
                          </span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {mode === 'venta' && (
            /*
             * The wizard itself owns its title via the inner <h1> + the
             * "← Volver" link rendered above the wizard header when
             * onCancel is supplied (Venta line 236).
             */
            <Venta onSuccess={handleVentaSuccess} onCancel={handleVolver} />
          )}

          {mode === 'cupos' && detalle && (
            <div className="space-y-4" data-testid="suscripciones-cupos-detalle">
              <button
                type="button"
                onClick={handleVolver}
                className="text-sm text-muted-foreground hover:underline"
                data-testid="suscripciones-cupos-volver"
              >
                ← {t('suscripciones:sheet.volver', { defaultValue: 'Volver' })}
              </button>

              <div className="rounded border bg-card px-3 py-2 text-sm">
                <div className="font-medium">
                  {detalle.cliente.nombre} {detalle.cliente.apellido}
                </div>
                <div className="text-xs text-muted-foreground">
                  {detalle.cliente.numero_identificacion} · {detalle.plan.tipo}
                </div>
                <div
                  className="mt-1 text-xs font-medium"
                  data-testid="suscripciones-cupos-resumen"
                >
                  {t('suscripciones:sheet.cupoResumen', {
                    defaultValue: 'Cupo',
                  })}
                  : {detalle.vehiculos.length}/{detalle.cupo_maximo ?? '—'} (
                  {detalle.cupo_disponible ?? 0}{' '}
                  {t('suscripciones:sheet.libres', { defaultValue: 'libres' })})
                </div>
              </div>

              <ul className="space-y-1" data-testid="suscripciones-cupos-vehiculos">
                {detalle.vehiculos.map((v) => (
                  <li
                    key={v.uuid}
                    className="flex items-center justify-between rounded border px-3 py-1.5 text-sm"
                    data-testid={`suscripciones-cupos-vehiculo-${v.uuid}`}
                  >
                    <span className="font-mono uppercase">{v.placa}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={quitar.isMutating}
                      onClick={() => void handleQuitar(v.uuid)}
                      data-testid={`suscripciones-cupos-quitar-${v.uuid}`}
                    >
                      {t('suscripciones:sheet.quitar', { defaultValue: 'Quitar' })}
                    </Button>
                  </li>
                ))}
                {detalle.vehiculos.length === 0 && (
                  <li className="text-sm text-muted-foreground">
                    {t('suscripciones:sheet.sinVehiculos', {
                      defaultValue: 'Sin vehículos inscritos.',
                    })}
                  </li>
                )}
              </ul>

              {agregar.error && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                  data-testid="suscripciones-cupos-agregar-error"
                >
                  {agregar.error.message}
                </p>
              )}
              {quitar.error && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                  data-testid="suscripciones-cupos-quitar-error"
                >
                  {quitar.error.message}
                </p>
              )}

              {cupoLleno ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="suscripciones-cupos-lleno"
                >
                  {t('suscripciones:sheet.cupoLleno', {
                    defaultValue: 'Cupo completo — quitá un vehículo para agregar otro.',
                  })}
                </p>
              ) : (
                <form
                  className="flex gap-2"
                  onSubmit={(e) => void handleAgregar(e)}
                  data-testid="suscripciones-cupos-agregar-form"
                >
                  <Input
                    id="suscripciones-cupos-agregar-input"
                    name="placa"
                    value={nuevaPlaca}
                    onChange={(e) => setNuevaPlaca(e.target.value)}
                    placeholder={t('suscripciones:sheet.placaPlaceholder', {
                      defaultValue: 'Placa',
                    })}
                    data-testid="suscripciones-cupos-agregar-input"
                    aria-label={t('suscripciones:sheet.placaPlaceholder', {
                      defaultValue: 'Placa',
                    })}
                  />
                  <Button
                    type="submit"
                    variant="default"
                    disabled={agregar.isMutating}
                    data-testid="suscripciones-cupos-agregar-submit"
                  >
                    {t('suscripciones:sheet.agregar', { defaultValue: 'Agregar' })}
                  </Button>
                </form>
              )}
            </div>
          )}
        </div>

        {mode === 'list' && (
          <SheetFooter>
            <Button
              type="button"
              variant="default"
              onClick={handleNuevaVenta}
              data-testid="suscripciones-sheet-nueva-venta"
              className="w-full"
            >
              +{' '}
              {t('suscripciones:sheet.nuevaVenta', {
                defaultValue: 'Nueva venta de suscripción',
              })}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => close()}
              data-testid="suscripciones-sheet-cancelar"
              className="w-full"
            >
              {t('common:cancel', { defaultValue: 'Cancelar' })}
            </Button>
          </SheetFooter>
        )}
      </SheetContent>
    </Sheet>
  );
}
