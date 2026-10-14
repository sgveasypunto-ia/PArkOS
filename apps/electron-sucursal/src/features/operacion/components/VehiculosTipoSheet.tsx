/**
 * `<VehiculosTipoSheet />` — bottom sheet con las placas que están DENTRO
 * para un tipo de vehículo, abierto desde un chip de `<CuposLibresStrip />`.
 *
 * Mounted via `<DrawerHost>` cuando `openDrawer === 'vehiculos-tipo'`
 * (single-drawer invariant, REQ-OPS-138). El tipo viaja en
 * `useDashboardDrawerStore.tipoVehiculoUuid`.
 *
 * Datos: los mismos hooks que alimentan los chips (`useOcupacion`, SWR key
 * compartida) y "Vehículos dentro" (`useIngresosActivos`); se agrupa en el
 * cliente por `uuid_tipo_vehiculo`. Nada de lógica de negocio nueva: las
 * acciones sólo ENRUTAN a los drawers existentes (swap del single-drawer,
 * este sheet se desmonta):
 *   - "Registrar salida"  → `open('salida', …)` vía `openSalidaDeIngreso`
 *     (mismo helper que las filas de "Vehículos dentro").
 *   - "Reimprimir ticket" → `open('reimpresion', …)` con la placa (o el
 *     consecutivo si no hay placa) como término; `<ReimprimirTiquete>` lo
 *     resuelve y salta a su paso de motivo/cobro.
 *
 * Esc / overlay / X cierran vía `close()`; el foco vuelve al chip (Radix
 * FocusScope restaura el elemento activo previo al montar).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { useAuth } from '@parkos/ui-kit/hooks';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

import { formatHoraCorta } from '../../caja/lib/format';
import { useIngresosActivos } from '../hooks/useIngresosActivos';
import { useOcupacion } from '../hooks/useOcupacion';
import { openReimpresionDeIngreso, terminoReimpresion } from '../lib/openReimpresionDeIngreso';
import { openSalidaDeIngreso } from '../lib/openSalidaDeIngreso';

const TITLE_ID = 'vehiculos-tipo-title';
const ANCHOR_ID = 'vehiculos-tipo-row';

export function VehiculosTipoSheet(): JSX.Element {
  const { t } = useTranslation(['operacion']);
  const { sucursal } = useAuth();
  const uuid_sucursal = sucursal?.uuid ?? null;

  const openDrawerKind = useDashboardDrawerStore((s) => s.openDrawer);
  const tipoUuid = useDashboardDrawerStore((s) => s.tipoVehiculoUuid);
  const openDrawer = useDashboardDrawerStore((s) => s.open);
  const close = useDashboardDrawerStore((s) => s.close);

  const { data: ocupacion } = useOcupacion(uuid_sucursal);
  const items = useIngresosActivos(uuid_sucursal);
  const [query, setQuery] = useState('');

  const tipo = ocupacion?.items.find((it) => it.uuid_tipo_vehiculo === tipoUuid)?.tipo ?? '';

  const delTipo = useMemo(
    () => (items ?? []).filter((it) => it.uuid_tipo_vehiculo === tipoUuid),
    [items, tipoUuid],
  );
  const needle = query.trim().toLowerCase();
  const visibles = useMemo(
    () =>
      needle === ''
        ? delTipo
        : delTipo.filter((it) =>
            `${it.placa ?? ''} ${it.consecutivo ?? ''}`.toLowerCase().includes(needle),
          ),
    [delTipo, needle],
  );

  return (
    <Sheet
      open={openDrawerKind === 'vehiculos-tipo'}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <SheetContent
        side="bottom"
        data-testid="vehiculos-tipo-sheet"
        aria-labelledby={TITLE_ID}
        className="flex max-h-[70dvh] flex-col gap-4"
      >
        <SheetHeader className="pr-12">
          <div className="flex items-center gap-2">
            <SheetTitle id={TITLE_ID} className="uppercase">
              {t('operacion:vehiculosTipo.titulo', { tipo, defaultValue: '{{tipo}}' })}
            </SheetTitle>
            <span
              className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground"
              data-testid="vehiculos-tipo-count"
              aria-live="polite"
            >
              {t('operacion:vehiculosTipo.conteo', {
                count: delTipo.length,
                defaultValue_one: '{{count}} vehículo dentro',
                defaultValue_other: '{{count}} vehículos dentro',
              })}
            </span>
          </div>
          <SheetDescription className="sr-only">
            {t('operacion:vehiculosTipo.descripcion', {
              tipo,
              defaultValue:
                'Vehículos dentro de tipo {{tipo}}, con acciones de salida y reimpresión de tiquete.',
            })}
          </SheetDescription>
        </SheetHeader>

        {delTipo.length > 0 && (
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="vehiculos-tipo-search"
            aria-label={t('operacion:vehiculosTipo.buscar', { defaultValue: 'Buscar placa' })}
            placeholder={t('operacion:vehiculosTipo.buscar', { defaultValue: 'Buscar placa' })}
            className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        )}

        <div className="min-h-0 flex-1 overflow-y-auto" data-testid="vehiculos-tipo-body">
          {items === null ? (
            <p className="text-sm text-muted-foreground" data-testid="vehiculos-tipo-loading">
              {t('operacion:vehiculosTipo.cargando', { defaultValue: 'Cargando vehículos…' })}
            </p>
          ) : delTipo.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="vehiculos-tipo-empty">
              {t('operacion:vehiculosTipo.sinVehiculos', {
                defaultValue: 'No hay vehículos de este tipo dentro.',
              })}
            </p>
          ) : visibles.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="vehiculos-tipo-no-match">
              {t('operacion:vehiculosTipo.sinResultados', {
                defaultValue: 'Ninguna placa coincide con la búsqueda.',
              })}
            </p>
          ) : (
            <ul className="divide-y divide-border/40" data-testid="vehiculos-tipo-list">
              {visibles.map((it) => {
                // Mismo identificador visible que "Vehículos dentro".
                const idVisible = it.placa ?? it.consecutivo ?? it.uuid.slice(0, 8);
                // Término que `resolverIngresoReimpresion` entiende (placa o
                // consecutivo); sin ninguno no hay forma de re-buscar el ingreso.
                const puedeReimprimir = terminoReimpresion(it) !== null;
                const anchorId = `${ANCHOR_ID}-${it.uuid}`;
                return (
                  <li
                    key={it.uuid}
                    data-testid={`vehiculos-tipo-row-${it.uuid}`}
                    className="flex items-center justify-between gap-3 px-3 py-2"
                  >
                    <div className="flex min-w-0 items-baseline gap-3">
                      <span
                        className="font-mono text-sm font-medium uppercase tracking-wide"
                        title={it.uuid}
                      >
                        {idVisible}
                      </span>
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {formatHoraCorta(it.fecha_ingreso ?? it.created_at)}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        id={anchorId}
                        data-testid={`vehiculos-tipo-salida-${it.uuid}`}
                        aria-label={t('operacion:vehiculosTipo.registrarSalidaDe', {
                          id: idVisible,
                          defaultValue: 'Registrar salida de {{id}}',
                        })}
                        onClick={() => openSalidaDeIngreso(openDrawer, anchorId, it)}
                        className="h-8 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {t('operacion:vehiculosTipo.registrarSalida', {
                          defaultValue: 'Registrar salida',
                        })}
                      </button>
                      {puedeReimprimir && (
                        <button
                          type="button"
                          data-testid={`vehiculos-tipo-reimprimir-${it.uuid}`}
                          aria-label={t('operacion:vehiculosTipo.reimprimirDe', {
                            id: idVisible,
                            defaultValue: 'Reimprimir ticket de {{id}}',
                          })}
                          onClick={() => openReimpresionDeIngreso(openDrawer, anchorId, it)}
                          className="h-8 rounded-lg border border-border bg-background px-3 text-xs font-medium transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {t('operacion:vehiculosTipo.reimprimir', {
                            defaultValue: 'Reimprimir ticket',
                          })}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
