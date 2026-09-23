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
 */
import { useCallback, useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

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
import {
  buscarIngresoTolerante,
  type ToleranteResultado,
} from '../../../lib/validation/placaTolerante';
import { getIngresosByPlaca, getIngresoEstado } from '../api/ingresoActivoApi';
import { SalidaFlow } from './SalidaFlow';
import { SalidaMensualidad } from './SalidaMensualidad';
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
}

export function SalidaPanel({
  uuid_ingreso: uuid_ingresoProp,
  initialPlaca = null,
}: SalidaPanelProps): JSX.Element {
  const { t } = useTranslation(['operacion', 'facturacion']);
  const openDrawer = useDashboardDrawerStore((s) => s.openDrawer);
  const open = useDashboardDrawerStore((s) => s.open);
  const pagoAnchorId = useId();

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
   */
  const [ingresoCerradoPlaca, setIngresoCerradoPlaca] = useState<string | null>(null);
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

  const { data: cotizacion, error: cotError, refresh } = useCotizacion(uuid_ingreso);

  const handlePlacaSubmit = form.handleSubmit(async (values) => {
    setPlaca(values.placa);
    setTolerante(null);
    setResolvedUuid(null);
    setIngresoCerradoPlaca(null);
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
        // estado del ingreso ANTES de setear ``resolvedUuid``: si
        // está cerrado, mostramos el mensaje específico y no
        // disparamos el fetch. La validación es una llamada extra
        // (``GET /ingresos/{uuid}/estado``) pero es barata (<50ms) y
        // evita un round-trip fallido a ``/cotizar``.
        try {
          const estado = await getIngresoEstado(resultado.uuid_ingreso);
          if (estado.estado === 'cerrado' || estado.estado === 'anulada') {
            setIngresoCerradoPlaca(resultado.placaReal);
            return;
          }
        } catch {
          // Si el lookup de estado falla (4xx/5xx), seguimos con el
          // flujo normal — el operador verá el error de
          // ``/cotizar`` si el ingreso realmente no se puede cotizar.
          // Mejor intentar que bloquear el flujo.
        }
        setResolvedUuid(resultado.uuid_ingreso);
      }
    } catch {
      setTolerante({ kind: 'none', placaProbada: values.placa });
    }
  });

  const handleOpenPago = useCallback(() => {
    // F8.1 (HU-F8.1 — PagoModal) — push the live cotizacion context
    // onto the drawer store BEFORE opening the `pago` drawer. The
    // `<DrawerHost>` reads `pagoContext` and forwards it to
    // `<PagoSheet>` so the form can build the
    // `POST /facturacion/factura` body without re-fetching the
    // cotizacion. `uuid_ingreso` is the Path-1 result from the parent
    // (typed via the `SalidaPanelProps.uuid_ingreso` prop); the
    // `total_cop` is the freshly-validated `cotizacion.total` that
    // the operator just approved by clicking "Cobrar".
    if (!uuid_ingreso || !cotizacion || cotizacion.cobrar === false) {
      return;
    }
    open('pago', pagoAnchorId, null, {
      uuid_ingreso,
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
                  <Input
                    id="salida-placa"
                    data-testid="salida-placa"
                    placeholder="ABC123"
                    {...field}
                  />
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

      {ingresoCerradoPlaca && (
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
              {ingresoCerradoPlaca}
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
            <SalidaMensualidad uuidIngreso={uuid_ingreso} />
          ) : cotizacion ? (
            <SalidaFlow
              uuidIngreso={uuid_ingreso}
              cotizacion={cotizacion}
              secondsLeft={secondsLeft}
              error={cotError}
              pagoAnchorId={pagoAnchorId}
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
