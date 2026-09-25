/**
 * `<SalidaPanel />` — F7.1+F7.2 dashboard section for vehicle-exit.
 *
 * Composes:
 *   - Plate input that calls `buscarIngresoTolerante(placa)` on submit
 *     (DEC-SUC-22 tolerance: `O↔0`/`I↔1`/`B↔8`).
 *   - `useCotizacion(uuid_ingreso)` polling via canonical F1.8
 *     discriminated union (REQ-OPS-143).
 *   - `<CotizacionPanel />` renders the breakdown `<dl>` (rotación) or
 *     mensualidad info banner.
 *   - `<PagoSheet />` trigger that opens the right-side drawer.
 *
 * REQ-OPS-138 (single-drawer): the panel does NOT maintain its own
 * drawer state — it calls `useDashboardDrawerStore.open('pago', anchorId)`
 * on demand. The PagoSheet subscribes to the same store and renders
 * exactly one drawer at a time.
 *
 * REQ-OPS-139 (lazy-mount): until the operator types a plate and the
 * server returns an active `uuid_ingreso`, `useCotizacion` key is
 * `null` and no `/cotizar` fetch is issued.
 *
 * REQ-OPS-146 (countdown): `useCountdown(15 * 60)` from F3.2 feeds the
 * `<CotizacionPanel />` countdown; <120s flips to destructive UX.
 *
 * HU-F7.1 (búsqueda sin placa, T5): the `salida-placa` field ALSO
 * autocompletes against the branch's live active-ingresos snapshot
 * (`useIngresosActivos` + `matchVehiculos`) so the operator can find a
 * no-placa vehicle (bici/patineta, identified only by `consecutivo`)
 * without leaving this field. Selecting a suggestion with a placa
 * reuses `handlePlacaSubmit` (the SAME tolerant-search + estado-guard
 * path as a manual submit); selecting one without a placa runs the
 * estado-guard directly against the candidate's `uuid_ingreso`.
 */
import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@parkos/ui-kit/hooks';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';

import { useCountdown } from '../../auth/hooks/useCountdown';
import { useCotizacion } from '../hooks/useCotizacion';
import { useIngresosActivos } from '../hooks/useIngresosActivos';
import {
  buscarIngresoTolerante,
  type ToleranteResultado,
} from '../../../lib/validation/placaTolerante';
import { getIngresosByPlaca, getIngresoEstado } from '../api/ingresoActivoApi';
import {
  matchVehiculos,
  vehiculoSuggestionOptionId,
  getNextSuggestionIndex,
  type VehiculoMatch,
} from '../lib/vehiculoMatch';
import { SalidaFlow } from './SalidaFlow';
import { SalidaMensualidad } from './SalidaMensualidad';
import { VehiculoSuggestions } from './VehiculoSuggestions';
import { useDashboardDrawerStore } from '@/store/dashboardDrawerStore';

const placaSchema = z.object({
  placa: z.string().trim().min(5, 'placa_formato_invalido'),
});
type PlacaValues = z.infer<typeof placaSchema>;

const COTIZAR_VIDA_UTIL_S = 15 * 60;

export interface SalidaPanelProps {
  /**
   * The active ingreso UUID selected by the operator (Path 1 result
   * from `useIngresoActivo(placa)` on the parent). `null` keeps the
   * panel in idle mode (REQ-OPS-139).
   */
  uuid_ingreso: string | null;
  /**
   * Optional plate pre-fill from the dashboard's PlacaInputHero. When
   * provided, the panel's placa form is pre-filled on mount so the
   * operator only has to press Enter to cotizar. We DO NOT auto-submit.
   */
  initialPlaca?: string | null;
  /**
   * HU-F7.1 (búsqueda sin placa) — `uuid_ingreso` resolved directly by
   * the dashboard's PlacaInputHero when the operator selects a NO-placa
   * suggestion (identified only by `consecutivo`). When provided, the
   * panel runs the SAME estado-guard (`getIngresoEstado`) already used
   * for the tolerant placa search before trusting the uuid — an
   * ingreso can appear "activo" in a stale 10s-polling snapshot but
   * already have a registered salida.
   */
  initialUuidIngreso?: string | null;
  /**
   * HU-F7.1 bugfix (found in live browser validation, not caught by
   * component-only tests): reports whenever the `salida-placa`
   * suggestion listbox opens/closes. `<SalidaSheet />` uses this to
   * wire `<SheetContent onEscapeKeyDown>` — Radix's Dialog attaches
   * its Escape-to-close listener on `document` with `capture: true`,
   * which fires BEFORE this panel's own bubble-phase `onKeyDown` on
   * the field ever runs. Without this callback, Escape-to-close-the-
   * suggestions always also closes the WHOLE Sheet (losing whatever
   * the operator typed), because the parent has no way to know a
   * nested popup should absorb that Escape first.
   */
  onSuggestionsOpenChange?: (open: boolean) => void;
}

export function SalidaPanel({
  uuid_ingreso: uuid_ingresoProp,
  initialPlaca = null,
  initialUuidIngreso = null,
  onSuggestionsOpenChange,
}: SalidaPanelProps): JSX.Element {
  const { t } = useTranslation(['operacion', 'facturacion']);
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const open = useDashboardDrawerStore((s) => s.open);
  const pagoAnchorId = useId();
  const listboxId = useId();

  const [placa, setPlaca] = useState<string | null>(null);
  const [tolerante, setTolerante] = useState<ToleranteResultado | null>(null);
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): cuando el
   * operador tipea una placa cuyo ingreso YA TIENE SALIDA registrada
   * (TST999, etc), ``buscarIngresoTolerante`` matchea la fila cerrada
   * y ``useCotizacion`` falla con 404 ``ingreso_no_encontrado``. Sin
   * este state, el operador ve "No se pudo obtener la cotización" sin
   * entender por qué. El nuevo state guarda el mensaje específico
   * ("ya tiene salida") y NO setea ``resolvedUuid`` para que no se
   * dispare el fetch fallido.
   *
   * HU-F7.1 (búsqueda sin placa): generalizado más allá de "placa" —
   * guarda cualquier identificador visible (placa O consecutivo) del
   * ingreso ya cerrado, porque `initialUuidIngreso` y las sugerencias
   * sin placa reusan la MISMA guarda de estado.
   */
  const [ingresoCerradoIdentificador, setIngresoCerradoIdentificador] = useState<string | null>(
    null,
  );
  /** HU-F7.1 — highlighted index in the `salida-placa` suggestion listbox. */
  const [activeIndex, setActiveIndex] = useState(-1);
  /** HU-F7.1 — Escape (or a submit) closes the suggestion listbox until the operator types again. */
  const [suggestionsClosed, setSuggestionsClosed] = useState(false);
  /**
   * REGRESSION fix (2026-09-22, directiva del operador): el
   * ``<SalidaSheet />`` padre pasa ``uuid_ingreso={null}`` siempre
   * (no tiene contexto del uuid del candidato encontrado vía búsqueda
   * tolerante). Sin este state local, ``useCotizacion(uuid_ingreso)``
   * recibe ``null`` y nunca dispara el fetch de
   * ``GET /api/v1/operacion/cotizar`` — el panel queda
   * eternamente en ``Cotizando…`` y nunca muestra tiempo + valor.
   *
   * El state ``resolvedUuid`` se llena cuando
   * ``buscarIngresoTolerante`` retorna ``kind: 'found'`` con un único
   * candidato. La prop ``uuid_ingresoProp`` gana sobre el state
   * local si está populada (defense-in-depth: si en el futuro el
   * padre quiere pasar el uuid directamente, no lo pisamos).
   */
  const [resolvedUuid, setResolvedUuid] = useState<string | null>(null);
  const uuid_ingreso = uuid_ingresoProp ?? resolvedUuid;

  const form = useForm<PlacaValues>({
    resolver: zodResolver(placaSchema),
    defaultValues: { placa: '' },
    mode: 'onSubmit',
  });

  // HU-F7.1 (búsqueda sin placa) — autocomplete deps. `useAuth()` is the
  // single source of truth for the branch UUID (same pattern
  // `<IngresoPanel />` already uses); `useIngresosActivos` gives the
  // panel its own live "vehículos dentro" snapshot so it can suggest
  // matches WITHOUT the operator having typed anything in the dashboard
  // hero first (F2 / botón lateral direct-open case).
  const { sucursal } = useAuth();
  const itemsActivos = useIngresosActivos(sucursal?.uuid ?? null);
  const placaFieldValue = form.watch('placa');
  const candidates = useMemo(
    () => matchVehiculos(itemsActivos ?? [], placaFieldValue ?? ''),
    [itemsActivos, placaFieldValue],
  );
  const isSuggestionsOpen = !suggestionsClosed && candidates.length > 0;
  const activeOptionId =
    activeIndex >= 0 ? vehiculoSuggestionOptionId(listboxId, activeIndex) : undefined;

  // HU-F7.1 bugfix — let the parent Sheet know whether the suggestion
  // popup is open so it can absorb Escape at the SheetContent level
  // (see `onSuggestionsOpenChange` doc above). `useEffect` (not inline
  // during render) because calling a parent state setter during this
  // component's own render is unsafe.
  useEffect(() => {
    onSuggestionsOpenChange?.(isSuggestionsOpen);
  }, [isSuggestionsOpen, onSuggestionsOpenChange]);

  /**
   * Estado-guard factored out so it runs IDENTICALLY regardless of the
   * entry point: the tolerant placa search below (`handlePlacaSubmit`),
   * the `initialUuidIngreso` mount-effect, and an in-field suggestion
   * click all funnel through here instead of duplicating the
   * try/catch. On `abierto`: sets `resolvedUuid`. On
   * `cerrado`/`anulada`: sets `ingresoCerradoIdentificador` (reusing the
   * SAME "ya tiene salida" card) and does NOT set `resolvedUuid`.
   */
  const resolveIngresoConGuarda = useCallback(
    async (uuidIngreso: string, identificador: string): Promise<void> => {
      setResolvedUuid(null);
      setIngresoCerradoIdentificador(null);
      try {
        const estado = await getIngresoEstado(uuidIngreso);
        if (estado.estado === 'cerrado' || estado.estado === 'anulada') {
          setIngresoCerradoIdentificador(identificador);
          return;
        }
      } catch {
        // Si el lookup de estado falla (4xx/5xx), seguimos con el flujo
        // normal — el operador verá el error de `/cotizar` si el
        // ingreso realmente no se puede cotizar. Mejor intentar que
        // bloquear el flujo (mismo criterio que el submit de placa).
      }
      setResolvedUuid(uuidIngreso);
    },
    [],
  );

  // Pre-fill placa on mount so the operator only has to press Enter
  // to trigger the cotizacion flow. We do not auto-submit.
  useEffect(() => {
    if (!initialPlaca) return;
    form.setValue('placa', initialPlaca.toUpperCase().replace(/\s+/g, ''), {
      shouldValidate: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPlaca]);

  // REGRESSION fix (2026-09-22, directiva del operador): cuando el
  // SalidaPanel monta con ``initialPlaca !== null`` (vino del smart
  // routing del PlacaInputHero), auto-disparamos el cotizacion para que
  // el operador vea tiempo + valor SIN un segundo Enter. Sin este
  // auto-submit, el flujo queda como: tipear placa → Enter → abre
  // SalidaSheet → ver form con placa prefilled → Enter de nuevo → ver
  // tiempo + valor. Dos Enters para llegar al dato que el operador
  // quiere ver (es la razón de este PR — "valor de parqueo" debe ser
  // visible inmediatamente).
  //
  // We use ``form.handleSubmit`` (RHF) so Zod validation runs against
  // the placa schema (``min(5, 'placa_formato_invalido')``). The
  // ``handlePlacaSubmit`` resolves to ``buscarIngresoTolerante`` →
  // ``setTolerante`` → ``useCotizacion`` reactivo → render del
  // ``<CotizacionPanel />`` con subtotal / iva / total / tiempo_minutos.
  //
  // Safety: the parent ``SalidaSheet`` only opens the drawer after
  // the smart-routing fetch confirmed ``rows.length > 0``, so the
  // plate WILL resolve to an active ingreso on the first attempt. If
  // Zod rejects (e.g. typo brings the placa below 5 chars), the
  // operator sees the inline ``FormMessage`` and can correct.
  useEffect(() => {
    if (!initialPlaca) return;
    // Wait one microtask so the form value set above propagates
    // through React before we call handleSubmit — otherwise RHF reads
    // the stale empty default and Zod rejects with
    // ``placa_formato_invalido``.
    const timer = setTimeout(() => {
      void handlePlacaSubmit();
    }, 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPlaca]);

  // HU-F7.1 (búsqueda sin placa): when the dashboard hero resolves a
  // NO-placa suggestion, it hands off the `uuid_ingreso` directly
  // (bypassing the tolerant placa search entirely — there is no placa
  // text to search for). Runs the SAME estado-guard as the placa path.
  useEffect(() => {
    if (!initialUuidIngreso) return;
    void resolveIngresoConGuarda(initialUuidIngreso, initialUuidIngreso);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialUuidIngreso]);

  const { data: cotizacion, error: cotError, refresh } = useCotizacion(uuid_ingreso);

  const handlePlacaSubmit = form.handleSubmit(async (values) => {
    setPlaca(values.placa);
    setTolerante(null);
    setResolvedUuid(null);
    setIngresoCerradoIdentificador(null);
    setSuggestionsClosed(true);
    try {
      const resultado = await buscarIngresoTolerante(values.placa, getIngresosByPlaca);
      setTolerante(resultado);
      // REGRESSION fix (2026-09-22): cuando el candidato es único,
      // resolvemos el uuid en el state local para que
      // ``useCotizacion`` pueda fetchar. El componente padre
      // (``<SalidaSheet />``) pasa ``uuid_ingreso={null}`` siempre, así
      // que este state es la única fuente de verdad para la cotizacion.
      if (resultado.kind === 'found') {
        // Defense in depth: si la placa matchea un ingreso que YA
        // TIENE SALIDA registrada (caso típico: el operador tipea una
        // placa que salió hace poco, o que se cerró en un test
        // anterior), ``useCotizacion`` va a fallar con 404
        // ``ingreso_no_encontrado`` y el operador verá "No se pudo
        // obtener la cotización" sin entender por qué. Validamos el
        // estado del ingreso ANTES de setear ``resolvedUuid`` — ver
        // `resolveIngresoConGuarda` (factorizada, HU-F7.1 T5).
        await resolveIngresoConGuarda(resultado.uuid_ingreso, resultado.placaReal);
      }
    } catch {
      setTolerante({ kind: 'none', placaProbada: values.placa });
    }
  });

  /**
   * HU-F7.1 — in-field suggestion selection. A placa candidate reuses
   * `handlePlacaSubmit` verbatim (tolerant search + estado-guard); a
   * no-placa candidate skips straight to the estado-guard with its
   * known `uuid_ingreso` (there is no placa to search for).
   */
  const selectSuggestionInField = useCallback(
    (candidate: VehiculoMatch): void => {
      setActiveIndex(-1);
      setSuggestionsClosed(true);
      const { ingreso } = candidate;
      if (ingreso.placa) {
        form.setValue('placa', ingreso.placa, { shouldValidate: false });
        // Mirrors the `initialPlaca` mount-effect precedent above: wait
        // one microtask so the form value propagates before
        // handleSubmit reads it — otherwise RHF can read the stale
        // (pre-selection) value.
        setTimeout(() => {
          void handlePlacaSubmit();
        }, 0);
      } else {
        void resolveIngresoConGuarda(ingreso.uuid, ingreso.consecutivo ?? ingreso.uuid);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [form, resolveIngresoConGuarda],
  );

  function handleFieldKeyDown(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (candidates.length === 0) return;
      e.preventDefault();
      setSuggestionsClosed(false);
      setActiveIndex((idx) =>
        getNextSuggestionIndex(idx, e.key === 'ArrowDown' ? 'down' : 'up', candidates.length),
      );
      return;
    }
    if (e.key === 'Escape') {
      if (isSuggestionsOpen) {
        // `stopPropagation` (not just `preventDefault`) is required:
        // `Dashboard.tsx` wires a GLOBAL `window.addEventListener(
        // 'keydown', ...)` that unconditionally closes any open drawer
        // on Escape (`if (openDrawerKind !== null) closeDrawer()`) —
        // it never checks `event.defaultPrevented`. Found via live
        // Chrome DevTools validation: with only `preventDefault()`,
        // selecting/dismissing a suggestion via Escape ALSO closed the
        // whole `<SalidaSheet />`, discarding whatever the operator had
        // typed. `SheetContent`'s `onEscapeKeyDown` (see
        // `<SalidaSheet />`) separately stops Radix's OWN
        // capture-phase Escape-to-dismiss, which runs before this
        // handler and does not share an event object with it.
        e.preventDefault();
        e.stopPropagation();
        setSuggestionsClosed(true);
        setActiveIndex(-1);
      }
      return;
    }
    if (e.key === 'Enter' && isSuggestionsOpen && activeIndex >= 0) {
      const candidate = candidates[activeIndex];
      if (candidate) {
        e.preventDefault();
        selectSuggestionInField(candidate);
      }
      return;
    }
    // Otherwise: fall through — native form submission handles Enter
    // exactly as before (RHF's onSubmit={handlePlacaSubmit}).
  }

  const handleOpenPago = useCallback((uuid_salida: string) => {
    // F8.1 (HU-F8.1 — PagoModal) — push the live cotizacion context
    // onto the drawer store BEFORE opening the `pago` drawer. The
    // `<DrawerHost>` reads `pagoContext` and forwards it to
    // `<PagoSheet>` so the form can build the
    // `POST /facturacion/factura` body without re-fetching the
    // cotizacion.
    //
    // `uuid_ingreso` is the Path-1 result from the parent (typed
    // via the `SalidaPanelProps.uuid_ingreso` prop).
    //
    // `uuid_salida` is the just-created `prod.salidas.uuid` from
    // `<SalidaFlow>`'s `useRegistrarSalida.trigger()` call —
    // F8.1-b (2026-09-23): required so `<PagoSheet>` can auto-annul
    // the salida on any close-without-pay path (Cancelar / X /
    // overlay click / Escape). Without it the ingreso would stay
    // `cerrado` and the cobro would be unrecoverable.
    //
    // `total_cop` / `subtotal_cop` are the freshly-validated
    // `cotizacion.total` / `cotizacion.subtotal` that the operator
    // just approved by clicking "Cobrar".
    if (!uuid_ingreso || !cotizacion || cotizacion.cobrar === false) {
      return;
    }
    open('pago', pagoAnchorId, null, {
      uuid_ingreso,
      uuid_salida,
      subtotal_cop: cotizacion.subtotal,
      total_cop: cotizacion.total,
    });
  }, [open, pagoAnchorId, uuid_ingreso, cotizacion]);

  // Countdown 15 min (REQ-OPS-146). `useCountdown` is reusable from F3.2.
  const { secondsLeft } = useCountdown(COTIZAR_VIDA_UTIL_S);

  return (
    <div className="space-y-4" data-testid="salida-panel">
      <Form {...form}>
        <form onSubmit={handlePlacaSubmit} className="space-y-2">
          <FormField
            control={form.control}
            name="placa"
            render={({ field }) => (
              <FormItem>
                <label htmlFor="salida-placa" className="text-sm font-medium">
                  {t('operacion:placa', { defaultValue: 'Placa' })}
                </label>
                <FormControl>
                  <div className="relative">
                    <Input
                      id="salida-placa"
                      data-testid="salida-placa"
                      placeholder="ABC123"
                      autoComplete="off"
                      role="combobox"
                      aria-expanded={isSuggestionsOpen}
                      aria-controls={listboxId}
                      aria-activedescendant={activeOptionId}
                      aria-autocomplete="list"
                      {...field}
                      onChange={(e) => {
                        field.onChange(e);
                        setActiveIndex(-1);
                        setSuggestionsClosed(false);
                      }}
                      onKeyDown={handleFieldKeyDown}
                      onBlur={() => {
                        field.onBlur();
                        setSuggestionsClosed(true);
                      }}
                    />
                    <VehiculoSuggestions
                      listboxId={listboxId}
                      testIdPrefix="salida-placa-suggestions"
                      candidates={isSuggestionsOpen ? candidates : []}
                      activeIndex={activeIndex}
                      onSelect={selectSuggestionInField}
                    />
                  </div>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" variant="outline" data-testid="salida-cotizar">
            {t('operacion:cotizar_boton', { defaultValue: 'Cotizar' })}
          </Button>
        </form>
      </Form>

      {ingresoCerradoIdentificador && (
        <Card data-testid="salida-ingreso-cerrado">
          <CardHeader>
            <CardTitle>
              {t('operacion:ingreso_cerrado_titulo', {
                defaultValue: 'Este ingreso ya tiene salida',
              })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('operacion:ingreso_cerrado_descripcion', {
                defaultValue:
                  'La placa que tipeaste corresponde a un ingreso que ya registró salida. Si necesitas reimprimir el tiquete, usa la opción Reimprimir del menú.',
              })}
            </p>
            <p className="mt-2 text-xs font-mono text-muted-foreground">
              {ingresoCerradoIdentificador}
            </p>
          </CardContent>
        </Card>
      )}

      {tolerante?.kind === 'multiple' && (
        <Card>
          <CardHeader>
            <CardTitle>
              {t('operacion:cotizar.candidatos_titulo', { defaultValue: 'Múltiples candidatos' })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {tolerante.candidatos.map((c) => (
                <li key={c.uuid_ingreso} data-testid={`candidato-${c.uuid_ingreso}`}>
                  {c.placaReal}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {tolerante?.kind === 'none' && (
        <p role="alert" className="text-sm text-destructive">
          {t('operacion:cotizar.errors.ingreso_no_encontrado', {
            defaultValue: 'No hay ingreso activo para esta placa en esta sucursal',
          })}
        </p>
      )}

      {uuid_ingreso && (cotizacion || cotError) && (
        <div data-anchor-for="pago" id={pagoAnchorId}>
          {cotizacion?.cobrar === false ? (
            // MIGRATION 0050 (operator directive 2026-09-24): pass the
            // live-polled cotizacion (full breakdown + descuento) down
            // so <SalidaMensualidad /> can build the discount factura
            // after the salida is confirmed — same pattern SalidaFlow
            // already uses for rotacion (subtotal_cop/total_cop below
            // come from this same `cotizacion` object, not a fresh
            // recompute).
            <SalidaMensualidad uuidIngreso={uuid_ingreso} cotizacion={cotizacion} />
          ) : cotizacion ? (
            <SalidaFlow
              uuidIngreso={uuid_ingreso}
              cotizacion={cotizacion}
              secondsLeft={secondsLeft}
              error={cotError}
              pagoAnchorId={pagoAnchorId}
              // HU-F8.1 regression fix: SalidaPanel owns the typed
              // `pagoContext` (uuid_ingreso + total_cop from the
              // cotizacion snapshot the operator just approved) and
              // hands it to the drawer store via `handleOpenPago`.
              // Without this, SalidaFlow falls back to opening the
              // `pago` drawer with NO context, which leaves
              // `<PagoSheet>` with `uuid_ingreso=null` (Confirm button
              // disabled) and `total_cop=0` (vueltos computation
              // broken). Production wiring MUST pass `onPagoOpen`.
              onPagoOpen={handleOpenPago}
              onRecalcular={() => {
                void refresh();
              }}
            />
          ) : (
            // cotizacion undefined + cotError set: render the error
            // banner via SalidaFlow (CotizacionPanel handles the error
            // branch internally). F7.1 behavior preserved.
            <SalidaFlow
              uuidIngreso={uuid_ingreso}
              cotizacion={{
                cobrar: true,
                subtotal: 0,
                iva: 0,
                total: 0,
                tiempo_minutos: 0,
                tarifa_uuid: '00000000-0000-0000-0000-000000000000',
                vigente_hasta: '1970-01-01T00:00:00Z',
              }}
              secondsLeft={secondsLeft}
              error={cotError}
              pagoAnchorId={pagoAnchorId}
              onRecalcular={() => {
                void refresh();
              }}
            />
          )}
        </div>
      )}

      {placa && !cotizacion && (
        <p className="text-sm text-muted-foreground" role="status">
          {t('operacion:cotizando', {
            defaultValue: 'Cotizando…',
          })}
        </p>
      )}

      {/* The drawer is mounted by <DrawerHost />; this panel just opens it. */}
      <input
        type="hidden"
        data-testid="salida-open-drawer-state"
        value={openDrawer === 'pago' ? 'open' : 'closed'}
      />
    </div>
  );
}
