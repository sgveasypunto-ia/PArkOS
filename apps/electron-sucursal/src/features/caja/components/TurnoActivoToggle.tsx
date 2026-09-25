/**
 * `<TurnoActivoToggle />` — persistent navbar element showing live turno
 * state with an in-place details toggle.
 *
 * Behavior:
 *   - Reads `useSesionActiva()` (F3.3, REQ-OPS-027).
 *   - When `data` is null, renders nothing (no turno open → no navbar entry).
 *   - When active, renders a compact chip + clickable toggle. Default state
 *     collapsed: shows `uuid corto + valores iniciales` + chevron.
 *   - On click, expands to show the FULL detail block previously held by
 *     `<TurnoActivoPanel />` (uuid, valores, apertura, observaciones)
 *     PLUS el resumen del turno abierto (operador 2026-09-22,
 *     reorganización visual del dashboard): 3 KPIs en línea —
 *     "Ingresos en mi turno" / "Salidas en mi turno" / "Cupos libres
 *     en la sucursal". Esos datos vienen de `useMiTurno(sesion.uuid)`
 *     y `useOcupacion(sesion.uuid_sucursal)` con cache compartida
 *     vía SWR deduping (mismo key que el `MiTurnoPanel` viejo
 *     consumía).
 *
 * Replaces the deprecated `<TurnoActivoPanel />` big card that lived in the
 * center column. The user wants the close-turn button ONLY in the navbar
 * (`<Dashboard />` header) and a toggle for details. Per their feedback
 * on 2026-09-17.
 *
 * **Histórico 2026-09-22:** las 3 filas del resumen del turno antes
 * vivían en el `<MiTurnoPanel />` del right-sidebar. Operador pidió
 * reubicarlas en este popover (donde el operador ya mira cuando quiere
 * ver detalles del turno). El componente sigue exportado y testeado
 * aislado — solo cambia quién lo usa en el Dashboard.
 *
 * Accessibility:
 *   - `<button aria-expanded="false" aria-controls="...">` (Disclosure WAI-ARIA).
 *   - Expanded content has `role="region" aria-labelledby="..."`.
 *   - Keyboard: Enter/Space toggles, Escape collapses (matches native
 *     `<details>`/`<summary>` semantics).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

import { useMiTurno } from '../../operacion/hooks/useMiTurno';
import { useOcupacion } from '../../operacion/hooks/useOcupacion';
import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';

export function TurnoActivoToggle({
  sesion,
}: {
  sesion: SesionRead | null;
}): JSX.Element | null {
  const { t } = useTranslation(['caja', 'operacion']);
  const [expanded, setExpanded] = useState(false);

  // Resumen del turno (operador 2026-09-22, directiva de reorganización
  // visual): antes vivía en `<MiTurnoPanel />` (right-sidebar). El
  // operador pidió moverlo al popover del navbar. Mismas fuentes de
  // datos (`useMiTurno` + `useOcupacion`), mismas reglas de zero-state
  // (sin sesion / sin branch → emdash, nunca inventar 0). SWR
  // deduping (5s) hace que el consumo aquí NO genere requests extra
  // si el `<MiTurnoPanel />` sigue montado en otra ruta.
  const uuidSesion = sesion?.uuid ?? null;
  const uuidSucursal = sesion?.uuid_sucursal ?? null;
  const { data: miTurnoData } = useMiTurno(uuidSesion);
  const { data: ocupacionData } = useOcupacion(uuidSucursal);

  const ingresosTurno = miTurnoData.ingresos_count;
  const salidasTurno = miTurnoData.salidas_count;
  const cuposLibres =
    ocupacionData?.items
      .filter((it) => it.cupo_maximo > 0)
      .reduce((acc, it) => acc + it.disponible, 0) ?? null;

  if (sesion === null) {
    return null;
  }

  const uuidCorto = sesion.uuid.slice(0, 8);
  const valores =
    formatCOP(sesion.valor_inicial_efectivo) +
    ' / ' +
    formatCOP(sesion.valor_inicial_datafono);

  // F11.x fix — el panel de detalles era un `<div absolute top-full>`
  // hecho a mano, sin portal ni collision detection: quedaba flotando
  // encima del `placa-card` de abajo en vez de desplazarse para no
  // taparlo. `<Popover>` (Radix, ya usado en el resto del proyecto)
  // portalea a `document.body` y su Popper calcula side/align con
  // collision detection automático — soluciona la superposición sin
  // gestionar manualmente Escape/foco (Radix ya implementa el patrón
  // WAI-ARIA disclosure/dialog: Escape cierra y devuelve foco al
  // trigger). Verificado en vivo con Chrome DevTools.
  return (
    <Popover open={expanded} onOpenChange={setExpanded}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={t('caja:dashboard.turnoActivoAria', {
            defaultValue: `Turno activo ${uuidCorto}, valores ${valores}. Click para ${expanded ? 'cerrar' : 'abrir'} detalles.`,
          })}
          data-testid="turno-activo-toggle"
          title={`${sesion.uuid} — click para ver detalles`}
          className="inline-flex h-8 items-center gap-1.5 rounded-full border border-emerald-200/60 bg-emerald-50/80 px-3 py-1 font-mono text-xs font-medium tracking-tight text-emerald-900 outline-none transition-all hover:bg-emerald-100/80 shadow-apple-sm focus-ring-apple"
        >
          <span
            aria-hidden
            className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500 ring-2 ring-emerald-100"
          />
          <span data-testid="turno-activo-toggle-uuid">{uuidCorto}…</span>
          <span aria-hidden className="opacity-40">·</span>
          <span data-testid="turno-activo-toggle-valores" className="tabular-nums">
            {valores}
          </span>
          <span aria-hidden className="ml-0.5 text-emerald-600">
            {expanded ? '▾' : '▸'}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        role="region"
        aria-label={t('caja:dashboard.turnoActivoDetalles', {
          defaultValue: 'Detalles del turno',
        })}
        data-testid="turno-activo-toggle-details"
        className="w-80 rounded-2xl border border-border/40 bg-popover p-4 text-sm shadow-apple-md"
      >
        <SesionDetails sesion={sesion} />
        <ResumenTurno
          ingresosTurno={ingresosTurno}
          salidasTurno={salidasTurno}
          cuposLibres={cuposLibres}
        />
      </PopoverContent>
    </Popover>
  );
}

/**
 * `<ResumenTurno />` — bloque interno del popover del navbar
 * (directiva operador 2026-09-22, reorganización visual del dashboard).
 *
 * Renderiza 3 KPIs en línea:
 *   1. Ingresos en mi turno (count, del MiTurnoRead)
 *   2. Salidas en mi turno (count, del MiTurnoRead)
 *   3. Cupos libres en la sucursal (sum de OcupacionItem.disponible,
 *      sólo items con cupo_maximo > 0)
 *
 * Cero-state: cuando el hook no popula, `useMiTurno` ya retorna
 * zero-payload (DA-F12.1-4) → los counts son `0`. `cuposLibres` puede
 * ser `null` (load-state) → emdash. Esto matchea exactamente la UX
 * del `<MiTurnoPanel />` que vivía antes en el right-sidebar.
 */
function ResumenTurno({
  ingresosTurno,
  salidasTurno,
  cuposLibres,
}: {
  ingresosTurno: number;
  salidasTurno: number;
  cuposLibres: number | null;
}): JSX.Element {
  const { t } = useTranslation(['caja', 'operacion']);
  return (
    <div
      data-testid="turno-activo-resumen"
      className="mt-3 border-t border-border/40 pt-3"
    >
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/80">
        {t('caja:dashboard.turnoActivoResumenTitulo', {
          defaultValue: 'Resumen del turno',
        })}
      </p>
      <ul
        role="list"
        className="divide-y divide-border/40 text-sm"
        data-testid="turno-activo-resumen-list"
      >
        <li
          data-testid="turno-activo-resumen-row-ingresos"
          className="flex items-center justify-between py-1.5"
        >
          <span className="text-muted-foreground/90 text-sm">
            {t('operacion:miTurno.kpis.ingresos', {
              defaultValue: 'Ingresos en mi turno',
            })}
          </span>
          <span className="font-mono text-base font-semibold tabular-nums tracking-tight">
            {ingresosTurno}
          </span>
        </li>
        <li
          data-testid="turno-activo-resumen-row-salidas"
          className="flex items-center justify-between py-1.5"
        >
          <span className="text-muted-foreground/90 text-sm">
            {t('operacion:miTurno.kpis.salidas', {
              defaultValue: 'Salidas en mi turno',
            })}
          </span>
          <span className="font-mono text-base font-semibold tabular-nums tracking-tight">
            {salidasTurno}
          </span>
        </li>
        <li
          data-testid="turno-activo-resumen-row-cupos-libres"
          className="flex items-center justify-between py-1.5"
        >
          <span className="text-muted-foreground/90 text-sm">
            {t('operacion:miTurno.kpis.cuposLibres', {
              defaultValue: 'Cupos libres en la sucursal',
            })}
          </span>
          <span
            data-testid="turno-activo-resumen-cupos-libres-value"
            className="font-mono text-base font-semibold tabular-nums tracking-tight"
          >
            {cuposLibres ?? '—'}
          </span>
        </li>
      </ul>
    </div>
  );
}

function SesionDetails({ sesion }: { sesion: SesionRead }): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <dl className="space-y-1.5">
      <div className="flex justify-between gap-2">
        <dt className="text-sm text-muted-foreground">UUID</dt>
        <dd
          className="truncate font-mono text-sm"
          title={sesion.uuid}
          data-testid="turno-activo-details-uuid"
        >
          {sesion.uuid}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-sm text-muted-foreground">
          {t('caja:valorInicialEfectivo', { defaultValue: 'Valor inicial efectivo' })}
        </dt>
        <dd
          className="font-mono text-sm"
          data-testid="turno-activo-details-valor-efectivo"
        >
          {formatCOP(sesion.valor_inicial_efectivo)}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-sm text-muted-foreground">
          {t('caja:valorInicialDatafono', { defaultValue: 'Valor inicial datáfono' })}
        </dt>
        <dd
          className="font-mono text-sm"
          data-testid="turno-activo-details-valor-datafono"
        >
          {formatCOP(sesion.valor_inicial_datafono)}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-sm text-muted-foreground">Apertura</dt>
        <dd className="font-mono text-sm" data-testid="turno-activo-details-apertura">
          {formatTiempoTranscurrido(sesion.timestamp_apertura)}
        </dd>
      </div>
      {sesion.observaciones !== null &&
        sesion.observaciones !== undefined &&
        sesion.observaciones !== '' && (
          <div className="flex justify-between gap-2">
            <dt className="text-sm text-muted-foreground">
              {t('caja:observaciones', { defaultValue: 'Observaciones' })}
            </dt>
            <dd
              className="max-w-[12rem] truncate text-right text-sm"
              data-testid="turno-activo-details-observaciones"
            >
              {sesion.observaciones}
            </dd>
          </div>
        )}
    </dl>
  );
}
