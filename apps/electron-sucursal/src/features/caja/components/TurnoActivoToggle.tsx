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
 *     `<TurnoActivoPanel />` (uuid, valores, apertura, observaciones).
 *
 * Replaces the deprecated `<TurnoActivoPanel />` big card that lived in the
 * center column. The user wants the close-turn button ONLY in the navbar
 * (`<Dashboard />` header) and a toggle for details. Per their feedback
 * on 2026-09-17.
 *
 * Accessibility:
 *   - `<button aria-expanded="false" aria-controls="...">` (Disclosure WAI-ARIA).
 *   - Expanded content has `role="region" aria-labelledby="..."`.
 *   - Keyboard: Enter/Space toggles, Escape collapses (matches native
 *     `<details>`/`<summary>` semantics).
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';

export function TurnoActivoToggle({
  sesion,
}: {
  sesion: SesionRead | null;
}): JSX.Element | null {
  const { t } = useTranslation('caja');
  const [expanded, setExpanded] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);

  // Collapse on Esc
  useEffect(() => {
    if (!expanded) return;
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') {
        setExpanded(false);
        buttonRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [expanded]);

  const buttonRef = useRef<HTMLButtonElement>(null);

  if (sesion === null) {
    return null;
  }

  const uuidCorto = sesion.uuid.slice(0, 8);
  const valores =
    formatCOP(sesion.valor_inicial_efectivo) +
    ' / ' +
    formatCOP(sesion.valor_inicial_datafono);

  const id = `turno-activo-toggle-${sesion.uuid}`;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={expanded}
        aria-controls={id}
        aria-label={t('caja:dashboard.turnoActivoAria', {
          defaultValue: `Turno activo ${uuidCorto}, valores ${valores}. Click para ${expanded ? 'cerrar' : 'abrir'} detalles.`,
        })}
        data-testid="turno-activo-toggle"
        onClick={() => setExpanded((v) => !v)}
        title={`${sesion.uuid} — click para ver detalles`}
        className="inline-flex h-7 items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-2.5 font-mono text-[11px] text-emerald-900 outline-none transition hover:bg-emerald-100 focus-visible:ring-2 focus-visible:ring-emerald-500"
      >
        <span
          aria-hidden
          className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"
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
        {expanded && (
        <div
          ref={detailsRef}
          id={id}
          role="region"
          aria-label={t('caja:dashboard.turnoActivoDetalles', {
            defaultValue: 'Detalles del turno',
          })}
          data-testid="turno-activo-toggle-details"
          className="absolute right-0 top-full z-30 mt-2 w-72 rounded-md border border-border bg-card p-3 text-xs shadow-lg"
        >
          <SesionDetails sesion={sesion} />
        </div>
      )}
    </div>
  );
}

function SesionDetails({ sesion }: { sesion: SesionRead }): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <dl className="space-y-1">
      <div className="flex justify-between gap-2">
        <dt className="text-muted-foreground">UUID</dt>
        <dd
          className="truncate font-mono"
          title={sesion.uuid}
          data-testid="turno-activo-details-uuid"
        >
          {sesion.uuid}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-muted-foreground">
          {t('caja:valorInicialEfectivo', { defaultValue: 'Valor inicial efectivo' })}
        </dt>
        <dd
          className="font-mono"
          data-testid="turno-activo-details-valor-efectivo"
        >
          {formatCOP(sesion.valor_inicial_efectivo)}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-muted-foreground">
          {t('caja:valorInicialDatafono', { defaultValue: 'Valor inicial datáfono' })}
        </dt>
        <dd
          className="font-mono"
          data-testid="turno-activo-details-valor-datafono"
        >
          {formatCOP(sesion.valor_inicial_datafono)}
        </dd>
      </div>
      <div className="flex justify-between gap-2">
        <dt className="text-muted-foreground">Apertura</dt>
        <dd className="font-mono" data-testid="turno-activo-details-apertura">
          {formatTiempoTranscurrido(sesion.timestamp_apertura)}
        </dd>
      </div>
      {sesion.observaciones !== null &&
        sesion.observaciones !== undefined &&
        sesion.observaciones !== '' && (
          <div className="flex justify-between gap-2">
            <dt className="text-muted-foreground">
              {t('caja:observaciones', { defaultValue: 'Observaciones' })}
            </dt>
            <dd
              className="max-w-[12rem] truncate text-right"
              data-testid="turno-activo-details-observaciones"
            >
              {sesion.observaciones}
            </dd>
          </div>
        )}
    </dl>
  );
}
