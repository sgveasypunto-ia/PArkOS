/**
 * `<ReimprimirTiquete />` — form/logic component (HU-F8.3, REQ-OPS-171).
 *
 * NO es una ruta (directiva del operador 2026-09-25): todo el flujo de
 * reimpresión con costo vive DENTRO de un drawer/sheet del dashboard —
 * mounts inside `<ReimprimirTiqueteSheet />` (`components/`), el
 * mismo patrón "thin shell wraps the form" que `<ArqueoSheet />` usa
 * para `pages/ArqueoParcial.tsx`. Sin conocimiento del Sheet que lo
 * envuelve (sin props, sin `useDashboardDrawerStore`) — el shell es
 * quien resuelve open/close/focus-restore. Composes:
 *
 *   - `resolverIngresoReimpresion(termino)` — resuelve placa O
 *     cupo/consecutivo (vehículo sin placa) a un `Ingreso` concreto,
 *     INCLUYENDO ingresos ya cerrados (el caso de uso típico es un
 *     tiquete perdido días después de que el vehículo salió). Reusa
 *     `matchVehiculos` + `<VehiculoSuggestions />` (mismo patrón que
 *     `<SalidaPanel />`, HU-F7.1) para el autocompletar in-field.
 *   - `useCostoServicioVigente('reimpresion')` — preview del costo
 *     vigente ANTES de cobrar (mismo espíritu que la cotización previa
 *     a `<PagoModal>` en salida).
 *   - `<PagoModal />` (REUSADO tal cual, sin fork) — mismo componente
 *     genérico que usa `<PagoSheet />` para el cobro de salida.
 *   - `useRegistrarPagoServicio()` — POST
 *     `/api/v1/facturacion/factura-servicio` (ajuste 2026-09-25,
 *     directiva del operador: la reimpresión tiene que disparar el
 *     MISMO flujo de cobro real que la salida — monto → método de
 *     pago → factura → tiquete de factura — no solo un snapshot
 *     interno). Endpoint NUEVO, no toca `create_factura` (esa ruta ya
 *     está en producción con DIAN/FE encima).
 *   - `useReimprimir()` — POST `/api/v1/workflows/reimpresion-ticket`
 *     con el `uuid_factura` real de la factura recién creada.
 *   - `<FacturaDisplayModal />` (REUSADO tal cual) — desglose completo
 *     post-cobro, mismo patrón que `<PagoSheet />`.
 *   - `useAnularReimpresion()` — POST `/{uuid}/anular` con INSERT-only
 *     chain invariant (F1.11 DEC-TKT-03) + motivo_anulacion Zod. Deja
 *     el registro de workflow como anulado pero NO reversa el pago/
 *     factura (decisión de alcance explícita, no un bug — reversar un
 *     cobro real es un flujo aparte de factura_pagos.reverse_payment,
 *     fuera de esta HU).
 *   - `escposBuilder.build('reimpresion', payload)` + `window.bridge
 *     .imprimir(...)` — reimpresión real del tiquete de entrada
 *     (best-effort, DEC-SUC-27, mismo patrón que `<IngresoPanel />`).
 *
 * El operador NUNCA tipea un UUID: la búsqueda resuelve `uuid_ingreso`
 * automáticamente.
 *
 * Alcance (2026-09-25): solo tiquetes de ENTRADA. Reimprimir un
 * tiquete de SALIDA necesita el desglose de cobro ORIGINAL
 * (subtotal/iva/total de `prod.facturas`/`factura_detalle`) — ningún
 * fetch del renderer lo expone hoy por `uuid_ingreso`, y recalcularlo
 * con una cotización fresca mostraría un monto distinto al realmente
 * cobrado (dato financiero incorrecto). Fuera de alcance aquí.
 *
 * Alcance de impresión (2026-09-25): el tiquete de entrada reimpreso
 * SÍ se imprime (buffer real vía `escposBuilder`). El recibo térmico
 * de la factura de servicio NO se imprime todavía — la plantilla
 * `'recibo_pago'` existente (`ReciboPagoPayload`) extiende
 * `SalidaPayload` (tarifa/tiempo parqueado/fecha de salida), campos
 * que una factura de servicio suelto no tiene; fabricarlos mostraría
 * datos incorrectos en el tiquete impreso. El desglose completo de la
 * factura SÍ se muestra en pantalla vía `<FacturaDisplayModal />`
 * (igual que `<PagoSheet />`). Una plantilla ESC/POS dedicada para
 * "factura de servicio suelto" queda como follow-up explícito.
 *
 * Rendering rules (REQ-OPS-171):
 *   - `motivo: z.string().min(10)` RHF + Zod resolver — checked BEFORE
 *     `<PagoModal />` se muestra, así el operador nunca ve un 400.
 *   - Success card renders uuid_reimpresion + costo_aplicado + motivo
 *     + "Anular" action que abre un alertdialog con motivo_anulacion.
 */
import { useCallback, useId, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { useAuth } from '@parkos/ui-kit/hooks';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { useIngresosActivos } from '../../operacion/hooks/useIngresosActivos';
import {
  matchVehiculos,
  vehiculoSuggestionOptionId,
} from '../../operacion/lib/vehiculoMatch';
import { VehiculoSuggestions } from '../../operacion/components/VehiculoSuggestions';
import type { Ingreso } from '../../operacion/api/ingresoActivoApi';
import { resolverIngresoReimpresion } from '../lib/resolverIngresoReimpresion';
import { formatCOP } from '../../caja/lib/format';
import { build as buildEscpos } from '../../../lib/print/escposBuilder';
import { buildReimpresionEntradaPayload } from '../../../lib/print/printBuilder';
import { useReimprimir } from '../hooks/useReimprimir';
import { useAnularReimpresion } from '../hooks/useAnularReimpresion';
import { useCostoServicioVigente } from '../hooks/useCostoServicioVigente';
import { useIvaVigente } from '../hooks/useIvaVigente';
import { useRegistrarPagoServicio } from '../hooks/useRegistrarPagoServicio';
import { PagoModal, type PagoFormValues } from '../components/PagoModal';
import { buildClienteFePayload } from '../lib/clienteFePayload';
import { FacturaDisplayModal } from '../components/FacturaDisplayModal';
import type { ReimpresionTicketRead } from '../api/reimpresionApi';
import type { FacturaRead } from '../api/facturaApi';
import type { PostFacturaServicioPayload } from '../api/facturaServicioApi';

const busquedaFormSchema = z.object({
  termino: z.string().trim().min(1, 'termino_requerido'),
});
type BusquedaFormValues = z.infer<typeof busquedaFormSchema>;

const motivoFormSchema = z.object({
  motivo: z.string().trim().min(10, 'motivo_muy_corto'),
});
type MotivoFormValues = z.infer<typeof motivoFormSchema>;

const anularFormSchema = z.object({
  motivo_anulacion: z.string().trim().min(10, 'motivo_anulacion_muy_corto'),
});
type AnularFormValues = z.infer<typeof anularFormSchema>;

function identificadorDe(ingreso: Ingreso): string {
  return ingreso.placa ?? ingreso.consecutivo ?? ingreso.uuid;
}

async function imprimirReimpresionEntrada(
  ingreso: Ingreso,
  motivo: string,
): Promise<void> {
  const payload = buildReimpresionEntradaPayload(ingreso, motivo);
  const buffer = buildEscpos('reimpresion', payload);
  await window.bridge.imprimir({
    buffer: buffer.toString('base64'),
    ticketId: ingreso.uuid,
    cut: true,
  });
}

export function ReimprimirTiquete(): JSX.Element {
  const { t } = useTranslation('facturacion');
  const { sucursal } = useAuth();

  const [busqueda, setBusqueda] = useState<
    | { kind: 'idle' }
    | { kind: 'multiple'; candidatos: Ingreso[] }
    | { kind: 'none'; termino: string }
  >({ kind: 'idle' });
  const [ingresoEncontrado, setIngresoEncontrado] = useState<Ingreso | null>(null);
  // HU-F8.3 (ajuste 2026-09-25): el motivo se confirma ANTES de mostrar
  // `<PagoModal />` (el operador nunca ve un 400 por motivo corto). Una
  // vez confirmado, este string es la fuente de verdad para el POST de
  // reimpresión — el form de motivo desaparece y el de pago lo reemplaza.
  const [motivoConfirmado, setMotivoConfirmado] = useState<string | null>(null);
  const [anularOpen, setAnularOpen] = useState(false);
  const [resultado, setResultado] = useState<ReimpresionTicketRead | null>(null);
  const [facturaDisplay, setFacturaDisplay] = useState<FacturaRead | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [suggestionsClosed, setSuggestionsClosed] = useState(false);

  const reimprimir = useReimprimir();
  const registrarPagoServicio = useRegistrarPagoServicio();
  const anular = useAnularReimpresion();
  const listboxId = useId();

  // HU-F8.3 (ajuste 2026-09-25): preview del costo vigente para el
  // concepto 'reimpresion' — se pide recién cuando hay un ingreso
  // encontrado (evita un fetch innecesario en el paso de búsqueda).
  const costoServicio = useCostoServicioVigente(
    ingresoEncontrado ? 'reimpresion' : null,
  );
  // BUGFIX (2026-09-25, encontrado por el operador con la factura
  // emitida real): `costos_servicios.costo` es el precio YA CON IVA
  // incluido (lo que el cliente paga), no una base a la que hay que
  // sumarle IVA encima. `subtotal`/`iva` mostrados en la factura deben
  // salir de ese precio, no coincidir con `total`.
  const ivaVigente = useIvaVigente(ingresoEncontrado !== null);

  const buscarForm = useForm<BusquedaFormValues>({
    resolver: zodResolver(busquedaFormSchema),
    defaultValues: { termino: '' },
    mode: 'onSubmit',
  });
  const motivoForm = useForm<MotivoFormValues>({
    resolver: zodResolver(motivoFormSchema),
    defaultValues: { motivo: '' },
    mode: 'onSubmit',
  });
  const anularForm = useForm<AnularFormValues>({
    resolver: zodResolver(anularFormSchema),
    defaultValues: { motivo_anulacion: '' },
    mode: 'onSubmit',
  });

  // Typeahead suggestions (HU-F7.1 pattern, mismo que <SalidaPanel />):
  // solo ingresos ACTIVOS de la sucursal actual — la resolución final al
  // enviar el formulario SÍ incluye histórico/cerrados vía
  // `resolverIngresoReimpresion`.
  const itemsActivos = useIngresosActivos(sucursal?.uuid ?? null);
  const terminoValue = buscarForm.watch('termino');
  const candidates = useMemo(
    () => matchVehiculos(itemsActivos ?? [], terminoValue ?? ''),
    [itemsActivos, terminoValue],
  );
  const isSuggestionsOpen = !suggestionsClosed && candidates.length > 0;
  const activeOptionId =
    activeIndex >= 0 ? vehiculoSuggestionOptionId(listboxId, activeIndex) : undefined;

  const resetBusqueda = useCallback(() => {
    setBusqueda({ kind: 'idle' });
    setIngresoEncontrado(null);
    setMotivoConfirmado(null);
    setErrorMsg(null);
  }, []);

  const resolverYSetear = useCallback(async (termino: string) => {
    setErrorMsg(null);
    setIngresoEncontrado(null);
    try {
      const resolucion = await resolverIngresoReimpresion(termino);
      if (resolucion.kind === 'found') {
        setBusqueda({ kind: 'idle' });
        setIngresoEncontrado(resolucion.ingreso);
      } else if (resolucion.kind === 'multiple') {
        setBusqueda({ kind: 'multiple', candidatos: resolucion.candidatos });
      } else {
        setBusqueda({ kind: 'none', termino: resolucion.termino });
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'error');
    }
  }, []);

  const handleBuscarSubmit = buscarForm.handleSubmit(async (values) => {
    setSuggestionsClosed(true);
    await resolverYSetear(values.termino);
  });

  // Selección desde la lista real de candidatos (`resolverIngresoReimpresion`,
  // ya tipada `Ingreso[]`) — DISTINTO de la sugerencia in-field (ver
  // `onSelect` de `<VehiculoSuggestions />` abajo), que solo trae un
  // `IngresoActivo` parcial (sin `uuid_subscripcion_cliente`) y por eso
  // re-dispara `resolverYSetear` en vez de usar el candidato directo.
  const seleccionarCandidato = useCallback((ingreso: Ingreso) => {
    setBusqueda({ kind: 'idle' });
    setIngresoEncontrado(ingreso);
  }, []);

  const handleMotivoSubmit = motivoForm.handleSubmit((values) => {
    setErrorMsg(null);
    setMotivoConfirmado(values.motivo);
  });

  const handlePago = useCallback(
    async (values: PagoFormValues): Promise<void> => {
      if (
        !ingresoEncontrado ||
        !motivoConfirmado ||
        costoServicio.costo === null ||
        ivaVigente.porcentaje === null
      ) {
        return;
      }
      const costo = costoServicio.costo;
      setErrorMsg(null);

      // BUGFIX (2026-09-25): `costo` ya incluye IVA (precio final al
      // cliente) — mismo criterio que `repo/factura.py::compute_total`
      // + `crear_factura_impuesto_iva` (DEC-FACT-03, mirror de la
      // PL/pgSQL `calcular_cotizacion`): `iva = round(total * tasa, 2)`,
      // `subtotal = total - iva`. `total` (lo cobrado) y
      // `items[0].valor_unitario` (lo que el backend recomputa y
      // compara contra `total`, V5) se mantienen en `costo` sin tocar.
      const ivaMonto = Math.round(costo * ivaVigente.porcentaje * 100) / 100;
      const subtotal = Math.round((costo - ivaMonto) * 100) / 100;

      const items = [
        {
          tipo: 'servicio' as const,
          concepto: 'Reimpresión de tiquete',
          cantidad: 1,
          valor_unitario: costo,
        },
      ];
      const feDatos = buildClienteFePayload(values);
      const post: PostFacturaServicioPayload =
        values.medio_pago === 'efectivo'
          ? {
              uuid_ingreso: ingresoEncontrado.uuid,
              medio_pago: 'efectivo',
              items,
              subtotal,
              total: costo,
              ...feDatos,
            }
          : {
              uuid_ingreso: ingresoEncontrado.uuid,
              medio_pago: 'datafono',
              items,
              subtotal,
              total: costo,
              referencia: values.voucher ?? '',
              ...feDatos,
            };

      try {
        // Paso 1: factura de servicio real (monto -> método de pago ->
        // factura), mismo motor que salida (KD-FACT-01).
        const factura = await registrarPagoServicio.trigger(post);
        // Paso 2: reimpresión del workflow, ahora con el uuid_factura
        // real (antes quedaba NULL — DEC-TKT-04 ya no aplica).
        const out = await reimprimir.trigger({
          uuid_ingreso: ingresoEncontrado.uuid,
          motivo: motivoConfirmado,
          uuid_factura: factura.uuid,
        });
        setResultado(out);
        setFacturaDisplay(factura);
        try {
          await imprimirReimpresionEntrada(ingresoEncontrado, motivoConfirmado);
        } catch {
          // Best-effort print (DEC-SUC-27) — el cobro y la reimpresión
          // ya quedaron registrados; un fallo de impresión no debe
          // bloquear ni revertir el flujo.
        }
      } catch (err) {
        setErrorMsg(err instanceof Error ? err.message : 'error');
      }
    },
    [
      ingresoEncontrado,
      motivoConfirmado,
      costoServicio.costo,
      ivaVigente.porcentaje,
      registrarPagoServicio,
      reimprimir,
    ],
  );

  const handleAnularConfirm = anularForm.handleSubmit(async (values) => {
    if (!resultado) return;
    try {
      await anular.trigger({
        uuidReimpresion: resultado.uuid,
        motivo_anulacion: values.motivo_anulacion,
      });
      setAnularOpen(false);
      setResultado(null);
      setFacturaDisplay(null);
      resetBusqueda();
      buscarForm.reset();
      motivoForm.reset();
      anularForm.reset();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'error');
    }
  });

  return (
    <article
      className="mx-auto max-w-2xl space-y-4 p-4"
      data-testid="reimprimir-tiquete-page"
    >
      {errorMsg && (
        <div
          role="alert"
          className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
          data-testid="reimprimir-error"
        >
          {errorMsg}
        </div>
      )}

      {resultado === null ? (
        <>
          {ingresoEncontrado === null && (
            <Form {...buscarForm}>
              <form
                onSubmit={handleBuscarSubmit}
                className="space-y-4"
                data-testid="reimprimir-buscar-form"
              >
                <FormField
                  control={buscarForm.control}
                  name="termino"
                  render={({ field }) => (
                    <FormItem>
                      {/* BUGFIX (2026-09-25, encontrado al validar con Chrome
                          DevTools): `FormLabel` setea `htmlFor={formItemId}`
                          apuntando a este `<div>` -- `FormControl`/`Slot`
                          inyecta ese id en su UNICO hijo directo, que aca es
                          el wrapper `relative`, no el `<input>` real (DevTools
                          reportaba "Incorrect use of <label for=FORM_ELEMENT>").
                          Mismo bug y mismo fix que `SalidaPanel.tsx` (HU-F7.1):
                          label manual + id explicito en el Input. */}
                      <label htmlFor="reimprimir-termino" className="text-sm font-medium">
                        {t('reimprimir.busqueda.label', {
                          defaultValue: 'Placa o cupo (vehículo sin placa)',
                        })}
                      </label>
                      <FormControl>
                        <div className="relative">
                          <Input
                            id="reimprimir-termino"
                            data-testid="reimprimir-termino"
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
                            onBlur={() => {
                              field.onBlur();
                              setSuggestionsClosed(true);
                            }}
                          />
                          <VehiculoSuggestions
                            listboxId={listboxId}
                            testIdPrefix="reimprimir-termino-suggestions"
                            candidates={isSuggestionsOpen ? candidates : []}
                            activeIndex={activeIndex}
                            onSelect={(candidate) => {
                              setSuggestionsClosed(true);
                              // `candidate.ingreso` es un `IngresoActivo`
                              // parcial (autocompletar in-field, HU-F7.1) —
                              // no alcanza para armar el tiquete (falta
                              // `uuid_subscripcion_cliente`). Se re-resuelve
                              // por el término para obtener el `Ingreso`
                              // completo, igual que el submit del form.
                              const termino =
                                candidate.ingreso.placa ??
                                candidate.ingreso.consecutivo ??
                                '';
                              buscarForm.setValue('termino', termino, {
                                shouldValidate: false,
                              });
                              void resolverYSetear(termino);
                            }}
                          />
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button type="submit" data-testid="reimprimir-buscar-confirmar">
                  {t('reimprimir.busqueda.buscar', { defaultValue: 'Buscar' })}
                </Button>
              </form>
            </Form>
          )}

          {busqueda.kind === 'none' && (
            <p role="alert" className="text-sm text-destructive" data-testid="reimprimir-no-encontrado">
              {t('reimprimir.busqueda.no_encontrado', {
                defaultValue: 'No se encontró ningún ingreso para "{{termino}}"',
                termino: busqueda.termino,
              })}
            </p>
          )}

          {busqueda.kind === 'multiple' && (
            <Card data-testid="reimprimir-candidatos">
              <CardHeader>
                <CardTitle>
                  {t('reimprimir.busqueda.candidatos_titulo', {
                    defaultValue: 'Múltiples candidatos',
                  })}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm">
                  {busqueda.candidatos.map((c) => (
                    <li key={c.uuid}>
                      <button
                        type="button"
                        className="w-full rounded-md border p-2 text-left hover:bg-accent"
                        data-testid={`reimprimir-candidato-${c.uuid}`}
                        onClick={() => seleccionarCandidato(c)}
                      >
                        {identificadorDe(c)} — {c.fecha_ingreso ?? '—'}
                      </button>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {ingresoEncontrado !== null && motivoConfirmado === null && (
            <Form {...motivoForm}>
              <form
                onSubmit={handleMotivoSubmit}
                className="space-y-4"
                data-testid="reimprimir-form"
              >
                <Card data-testid="reimprimir-ingreso-encontrado">
                  <CardHeader>
                    <CardTitle className="text-base">
                      {identificadorDe(ingresoEncontrado)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 text-sm text-muted-foreground">
                    <p>
                      {t('reimprimir.ingreso.fecha', { defaultValue: 'Ingreso' })}:{' '}
                      {ingresoEncontrado.fecha_ingreso ?? '—'}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      data-testid="reimprimir-cambiar-busqueda"
                      onClick={resetBusqueda}
                    >
                      {t('reimprimir.busqueda.cambiar', { defaultValue: 'Buscar otro' })}
                    </Button>
                  </CardContent>
                </Card>

                <FormField
                  control={motivoForm.control}
                  name="motivo"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        {t('reimprimir.motivoLabel', {
                          defaultValue: 'Motivo (mín. 10 caracteres)',
                        })}
                      </FormLabel>
                      <FormControl>
                        <Input
                          data-testid="reimprimir-motivo"
                          placeholder={t('reimprimir.motivoPlaceholder', {
                            defaultValue: 'Describe el motivo',
                          })}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Button type="submit" data-testid="reimprimir-continuar">
                  {t('reimprimir.continuar', { defaultValue: 'Continuar al cobro' })}
                </Button>
              </form>
            </Form>
          )}

          {ingresoEncontrado !== null && motivoConfirmado !== null && (
            <Card data-testid="reimprimir-cobro">
              <CardHeader>
                <CardTitle className="text-base">
                  {t('reimprimir.cobro.titulo', { defaultValue: 'Cobrar reimpresión' })}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {(costoServicio.isLoading || ivaVigente.isLoading) && (
                  <p className="text-sm text-muted-foreground" data-testid="reimprimir-costo-cargando">
                    {t('reimprimir.cobro.cargando', { defaultValue: 'Consultando costo vigente…' })}
                  </p>
                )}
                {!costoServicio.isLoading && costoServicio.costo === null && (
                  <p
                    role="alert"
                    className="text-sm text-destructive"
                    data-testid="reimprimir-costo-no-configurado"
                  >
                    {t('reimprimir.cobro.no_configurado', {
                      defaultValue:
                        'No hay un costo configurado para la reimpresión. Configuralo en costos de servicios antes de continuar.',
                    })}
                  </p>
                )}
                {!costoServicio.isLoading &&
                  !ivaVigente.isLoading &&
                  costoServicio.costo !== null &&
                  ivaVigente.porcentaje !== null && (
                  <>
                    <p className="mb-4 text-sm text-muted-foreground" data-testid="reimprimir-costo-vigente">
                      {t('reimprimir.cobro.monto', { defaultValue: 'Monto a cobrar' })}:{' '}
                      <span className="font-medium text-foreground">
                        {formatCOP(costoServicio.costo)}
                      </span>
                    </p>
                    <PagoModal
                      uuid_ingreso={ingresoEncontrado.uuid}
                      total_cop={costoServicio.costo}
                      onSubmit={handlePago}
                    />
                  </>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  data-testid="reimprimir-cambiar-motivo"
                  onClick={() => setMotivoConfirmado(null)}
                >
                  {t('reimprimir.cobro.volver', { defaultValue: 'Volver' })}
                </Button>
              </CardContent>
            </Card>
          )}
        </>
      ) : (
        <section
          className="space-y-3 rounded-md border bg-card p-4"
          data-testid="reimprimir-success"
        >
          <h2 className="text-lg font-semibold">
            {t('reimprimir.success.titulo', { defaultValue: 'Reimpresión registrada' })}
          </h2>
          <dl className="space-y-1 text-sm">
            <div>
              <dt className="font-medium">UUID</dt>
              <dd data-testid="reimprimir-success-uuid" className="break-all">{resultado.uuid}</dd>
            </div>
            <div>
              <dt className="font-medium">
                {t('reimprimir.success.costo', { defaultValue: 'Costo cobrado' })}
              </dt>
              <dd data-testid="reimprimir-success-costo">
                {resultado.costo_aplicado !== null
                  ? formatCOP(resultado.costo_aplicado)
                  : '—'}
              </dd>
            </div>
            <div>
              <dt className="font-medium">Motivo</dt>
              <dd className="break-words">{resultado.motivo}</dd>
            </div>
          </dl>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setAnularOpen(true)}
              data-testid="reimprimir-anular"
            >
              {t('reimprimir.anular.titulo', { defaultValue: 'Anular reimpresión' })}
            </Button>
            <Button
              type="button"
              onClick={() => {
                setResultado(null);
                setFacturaDisplay(null);
                resetBusqueda();
                buscarForm.reset();
                motivoForm.reset();
              }}
              data-testid="reimprimir-nuevo"
            >
              {t('reimprimir.nuevo', { defaultValue: 'Reimprimir otro' })}
            </Button>
          </div>
        </section>
      )}

      {/* HU-F8.3 (ajuste 2026-09-25) — desglose completo de la factura
          de servicio recién cobrada, mismo componente reusado tal cual
          que `<PagoSheet />` monta post-pago de salida. */}
      <FacturaDisplayModal
        factura={facturaDisplay}
        onClose={() => setFacturaDisplay(null)}
      />

      {/* REQ-OPS-174 — anulación dialog with motivo_anulacion.
          `modal={false}`: BUGFIX (2026-09-25, encontrado con Chrome
          DevTools) -- este Dialog vive DENTRO de `<ReimprimirTiqueteSheet />`,
          y `Sheet`/`Dialog` son AMBOS `DialogPrimitive.Root` de Radix
          (mismo primitivo). Dos `Root` modales anidados compiten por
          ocultar-todo-lo-demas via aria-hidden, y el navegador reportaba
          "Blocked aria-hidden on an element because its descendant
          retained focus" sobre el propio contenido del Sheet. El Sheet
          ya actua como barrera modal por fuera; este dialogo interno no
          necesita repetir el focus-trap/aria-hidden -- solo su propio
          contenido. */}
      <Dialog open={anularOpen} onOpenChange={setAnularOpen} modal={false}>
        <DialogContent
          role="alertdialog"
          data-testid="reimprimir-anular-dialog"
          aria-labelledby="reimprimir-anular-title"
          aria-describedby="reimprimir-anular-desc"
        >
          <DialogHeader>
            <DialogTitle id="reimprimir-anular-title">
              {t('reimprimir.anular.titulo', { defaultValue: 'Anular reimpresión' })}
            </DialogTitle>
            <DialogDescription id="reimprimir-anular-desc">
              {t('reimprimir.anular.descripcion', {
                defaultValue:
                  'La anulación registra una fila nueva en la cadena y no modifica la reimpresión original.',
              })}
            </DialogDescription>
          </DialogHeader>
          <Form {...anularForm}>
            <form onSubmit={handleAnularConfirm} className="space-y-4" data-testid="reimprimir-anular-form">
              <FormField
                control={anularForm.control}
                name="motivo_anulacion"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('reimprimir.anular.motivoLabel', {
                        defaultValue: 'Motivo de anulación (mín. 10 caracteres)',
                      })}
                    </FormLabel>
                    <FormControl>
                      <Input
                        data-testid="reimprimir-anular-motivo"
                        placeholder={t('reimprimir.motivoPlaceholder', {
                          defaultValue: 'Describe el motivo',
                        })}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAnularOpen(false)}
                  data-testid="reimprimir-anular-cancelar"
                >
                  {t('common:cancel', { defaultValue: 'Cancelar' })}
                </Button>
                <Button
                  type="submit"
                  disabled={anular.isMutating}
                  data-testid="reimprimir-anular-confirm"
                >
                  {t('reimprimir.anular.confirmar', { defaultValue: 'Anular' })}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </article>
  );
}
