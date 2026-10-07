/**
 * `<Venta />` — wizard of 6 steps for the subscription sale at the
 * counter (HU-F9.1, REQ-OPS-176; reordered in PT-2, back-navigation PT-1).
 *
 * Steps:
 *   1 — cliente {tipo_persona, tipo_identificador, numero_identificacion,
 *       dv?, nombre, apellido?} (`<ClienteIdentificacionFields>`)
 *   2 — tipo de vehículo (moto, carro, ...) from `catalogos/tipos-vehiculo`
 *   3 — plan: ONLY the plans of that vehicle type (+ the type-agnostic
 *       ones) via `GET /catalogos/tipo-subscripciones?uuid_tipo_vehiculo=`
 *   4 — cantidad de vehículos (1..plan.cantidad_maxima_vehiculos)
 *   5 — placas (exactly N, auto/moto format + matching the chosen type)
 *   6 — pago: `<PagoModal />` (F8.1 reuse)
 *
 * PT-1 — "Volver": a single control that goes back EXACTLY one step keeping
 * everything captured (cliente, tipo, plan, cantidad, placas, pago draft);
 * on step 1 it calls `onCancel` (back to the parent list). Changing the
 * type/plan/quantity invalidates only what depends on it. After a charged
 * sale it is hidden and the payment can no longer be re-sent.
 *
 * State machine: `useState<VentaStepState>`; each step has its own Zod
 * schema and advancing runs `safeParse` first (per-step validation).
 *
 * The 3 backend 422 error subclasses (duplicate plate, incompatible type,
 * max quantity) send the operator back to the placas step (5) with an
 * inline message.
 *
 * PT-3: the full plan price is ALWAYS charged (no proration). The electronic
 * invoice is ALWAYS emitted by the backend (consumidor final unless the
 * subscriber is billed); its state is shown in the receipt.
 *
 * On a charged sale the receipt is shown and then `onSuccess` (embedded) or a
 * navigation to `/suscripciones` runs.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { useAuth } from '@parkos/ui-kit/hooks';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { formatCOP } from '../../caja/lib/format';
import { PagoModal, type PagoFormValues } from '../../facturacion/components/PagoModal';
import { FacturaDisplayModal } from '../../facturacion/components/FacturaDisplayModal';
import {
  ClienteIdentificacionFields,
  type ClienteIdentificacionValue,
} from '../../facturacion/components/ClienteIdentificacionFields';
import type { FacturaRead } from '../../facturacion/api/facturaApi';

import {
  useVentaSuscripcion,
  VentaSuscripcionDuplicatePlateError,
  VentaSuscripcionTipoIncompatibleError,
  VentaSuscripcionCantidadMaximaError,
  type VentaSuscripcionCreate,
} from '../hooks/useVentaSuscripcion';
import { useTiposSubscripciones } from '../hooks/useTiposSubscripciones';
import { useTiposVehiculo } from '../../catalogos/hooks/useTiposVehiculo';
import { feWarningMessage } from '../../facturacion/lib/feEstado';
import { hoyBogotaISO } from '../lib/fechaInicio';
import { buildClienteVentaPayload } from '../lib/clienteVentaPayload';
import { validarIdentificacion } from '../../../lib/validation/identificacion';
import { validarNitModulo11 } from '../../../lib/validation/nit';

/**
 * Optional escape hatches for non-page consumers (e.g., embedded in
 * a drawer / sheet). Defaults preserve the page-route behavior
 * (navigate to /suscripciones on success) so existing callers (page
 * Venta + Venta.test.tsx) are unaffected.
 *
 * - `onSuccess()` fires AFTER the POST returns 2xx. Used by the sheet
 *   to close the drawer + refresh the subscription list.
 * - `onCancel()` fires when the operator presses "Volver" rendered
 *   at the top of the wizard when this callback is supplied. Lets the
 *   sheet return to the list view while keeping the wizard state for
 *   re-entry.
 * - `firePrintEnvelope()` — optional override for the post-pago recibo
 *   print (mirrors `PagoSheetProps.firePrintEnvelope` / F8.1). Defaults
 *   to `window.bridge?.imprimir('recibo_pago', payload)` via the same
 *   swallow-errors helper `<PagoSheet />` uses (DEC-SUC-08).
 */
export interface VentaProps {
  onSuccess?: () => void;
  onCancel?: () => void;
  firePrintEnvelope?: (tipo: 'recibo_pago', payload: unknown) => void;
}

function defaultFirePrintEnvelope(tipo: 'recibo_pago', payload: unknown): void {
  const w = globalThis as unknown as {
    window?: { bridge?: { imprimir?: (k: string, p: unknown) => void } };
  };
  const bridge = w.window?.bridge;
  if (bridge?.imprimir) {
    bridge.imprimir(tipo, payload);
  }
}

/**
 * F7.3 (DEC-SUC-08 + DEC-SUC-27) — defer the print envelope to the
 * next microtask so it never blocks the modal-dismiss render commit,
 * and swallow any bridge failure (printer offline / disconnected) so
 * a hardware issue never blocks the operator from finishing the sale.
 * Mirrors `<PagoSheet />`'s `deferredSafePrint` verbatim.
 */
function deferredSafePrint(
  emit: (tipo: 'recibo_pago', payload: unknown) => void,
  tipo: 'recibo_pago',
  payload: unknown,
): void {
  queueMicrotask(() => {
    try {
      emit(tipo, payload);
    } catch (err) {
      console.warn(
        `[Venta] bridge.imprimir(${tipo}) failed (printer_offline / disconnected):`,
        err,
      );
    }
  });
}

export interface VentaStepState {
  /** 1 cliente · 2 tipo de vehículo · 3 plan · 4 cantidad · 5 placas · 6 pago. */
  paso: 1 | 2 | 3 | 4 | 5 | 6;
  cliente?: ClienteIdentificacionValue;
  /** PT-2: chosen BEFORE the plan; the plan catalog is filtered by it. */
  uuid_tipo_vehiculo?: string;
  uuid_tipo_subscripcion?: string;
  /**
   * Number of vehicles the operator is going to associate with this
   * suscripcion (selected at step 3 "Cantidad"). Used to size the
   * placa inputs at step 4. Validated 1..plan.cantidad_maxima_vehiculos.
   */
  cantidad_vehiculos?: number;
  placas?: string[];
  fecha_inicio_cobertura?: string;
  monto_proporcional?: number | null;
}

/**
 * Paso 1 — identificación de cliente (ajuste persona natural/empresa).
 * Mirrors `PagoModal`'s `validarBloqueFe` cross-field rules but WITHOUT
 * the `fe` gate (paso 1 siempre exige un cliente real, no hay opción de
 * "cliente genérico" en una venta de suscripción). `dv` is OPTIONAL even
 * for NIT — same contract as backend `ClientesCreate._validar_nit_dv`
 * ("if dv is absent for a NIT, no-ops"): si el operador lo ingresa debe
 * ser correcto, pero no bloquea el avance si lo deja vacío.
 */
const clienteSchema = z
  .object({
    tipo_persona: z.enum(['persona', 'empresa']),
    tipo_identificador: z.enum(['NIT', 'CC', 'CE', 'pasaporte']),
    numero_identificacion: z.string().min(5, 'documento_min_5'),
    dv: z.string(),
    nombre: z.string().min(1, 'nombre_requerido'),
    apellido: z.string(),
  })
  .superRefine((values, ctx) => {
    if (values.tipo_identificador !== 'NIT') {
      const resultado = validarIdentificacion(
        values.tipo_identificador,
        values.numero_identificacion,
      );
      if (!resultado.ok) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['numero_identificacion'],
          message: resultado.motivo ?? 'documento_formato_invalido',
        });
      }
    } else {
      const dv = values.dv.trim();
      if (dv) {
        if (
          !/^[0-9]$/.test(dv) ||
          !validarNitModulo11(values.numero_identificacion, dv).ok
        ) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['dv'],
            message: 'dv_invalido',
          });
        }
      }
    }
    if (values.tipo_persona === 'persona' && !values.apellido.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['apellido'],
        message: 'apellido_requerido',
      });
    }
  });

const planSchema = z.object({
  uuid_tipo_subscripcion: z
    .string()
    .uuid('uuid_tipo_subscripcion_invalido'),
});

/**
 * `buildCantidadSchema(max)` -- F11.3 follow-up: operator picks how
 * many vehicles the suscripcion will cover at step 3. The upper bound
 * is the selected plan's `cantidad_maxima_vehiculos`. Per-plan
 * enforcement means we don't validate against a hardcoded global max
 * (MENSUAL_AUTO / MENSUAL_MOTO / BIMESTRAL_AUTO / TRIMESTRAL_AUTO
 * cap at 1; only MENSUAL_EMPRESA goes higher).
 */
const buildCantidadSchema = (max: number) =>
  z.object({
    cantidad_vehiculos: z.coerce
      .number({ invalid_type_error: 'validation.number.required' })
      .int()
      .min(1, 'validation.cantidad.min_1')
      .max(max, 'validation.cantidad.max_excedida'),
  });

/**
 * `buildPlacasSchema(count)` -- step 4 enforces that exactly `count`
 * plates are entered (no max(2) clamp anymore -- the count comes
 * from the operator's choice at step 3, validated against the plan
 * limit at step 2). Each plate must match the auto/moto regex.
 */
const buildPlacasSchema = (count: number) =>
  z.object({
    placas: z
      .array(
        z
          .string()
          .regex(
            /^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/,
            'placa_formato_invalido',
          ),
      )
      .length(count),
  });

/**
 * Default plan valor used for the payment preview when the operator
 * hasn't selected a plan yet. When a plan IS selected, its `valor`
 * drives the amount. The authoritative amount is computed server-side
 * at the POST (defense in depth -- the wizard's preview is informational).
 */
const PLAN_PREVIEW_VALOR = 30000;

const PLACA_AUTO = /^[A-Z]{3}[0-9]{3}$/;
const PLACA_MOTO = /^[A-Z]{3}[0-9]{2}[A-Z]$/;
const TOTAL_PASOS = 6;

export function Venta({
  onSuccess,
  onCancel,
  firePrintEnvelope,
}: VentaProps = {}): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const navigate = useNavigate();
  const { sucursal } = useAuth();
  const uuid_sucursal = sucursal?.uuid ?? null;
  const [state, setState] = useState<VentaStepState>({ paso: 1 });
  const [clienteIdent, setClienteIdent] = useState<ClienteIdentificacionValue>({
    tipo_persona: 'empresa',
    tipo_identificador: 'NIT',
    numero_identificacion: '',
    dv: '',
    nombre: '',
    apellido: '',
  });
  const [clienteErrors, setClienteErrors] = useState<
    Partial<Record<'numero_identificacion' | 'dv' | 'nombre' | 'apellido', string>>
  >({});
  // PT-2: vehicle type chosen BEFORE the plan (the plan catalog is filtered by it).
  const [tipoVehiculoInput, setTipoVehiculoInput] = useState('');
  const [planInput, setPlanInput] = useState('');
  const [cantidadError, setCantidadError] = useState<string | null>(null);
  const [cantidadInput, setCantidadInput] = useState('1');
  const [placasError, setPlacasError] = useState<string | null>(null);
  // Per-placa input draft state. Preserved across "Volver" (PT-1): going
  // back never discards what the operator already typed.
  const [placasInputs, setPlacasInputs] = useState<string[]>([]);
  // Generic inline error for the placas step -- shared by both duplicate-plate
  // 422 (server response) and invalid-format (local Zod).
  const [placaGroupError, setPlacaGroupError] = useState<string | null>(null);
  // PT-1: payment form values, kept while the operator steps back from the
  // payment step (and restored when returning to it).
  const [pagoDraft, setPagoDraft] = useState<PagoFormValues | null>(null);
  // HU-F9.1 bugfix (2026-09-25): hold the enriched `FacturaRead` the
  // backend returns when `cobrar_ahora=true` so we can mount
  // `<FacturaDisplayModal />` with the full breakdown before completing
  // the wizard.
  const [facturaDisplay, setFacturaDisplay] = useState<FacturaRead | null>(null);
  // Non-blocking FE notice (pending / failed-and-auto-retried).
  const [facturaElectronicaWarning, setFacturaElectronicaWarning] = useState<
    string | null
  >(null);
  // PT-1: once the sale is charged the wizard is FINAL -- "Volver" and a
  // second submit are disabled so the payment can never be re-sent.
  const [ventaCompletada, setVentaCompletada] = useState(false);
  const { trigger, isMutating } = useVentaSuscripcion();
  const { tipos: tiposVehiculo, isFromFallback: tiposFromFallback } = useTiposVehiculo();
  const {
    data: planes,
    error: planesError,
    isLoading: planesLoading,
  } = useTiposSubscripciones(uuid_sucursal, state.uuid_tipo_vehiculo ?? null);

  const selectedPlan = useMemo(() => {
    if (!planes || !state.uuid_tipo_subscripcion) return null;
    return (
      planes.find((p) => p.uuid === state.uuid_tipo_subscripcion) ?? null
    );
  }, [planes, state.uuid_tipo_subscripcion]);

  const selectedTipoVehiculo = useMemo(
    () => tiposVehiculo.find((tv) => tv.uuid === state.uuid_tipo_vehiculo) ?? null,
    [tiposVehiculo, state.uuid_tipo_vehiculo],
  );

  // Stable prefill: PagoModal reads it through a ref, but keeping the
  // identity stable avoids needless re-renders of the payment form.
  const clientePrefill = useMemo(
    () => ({
      nit: state.cliente?.numero_identificacion ?? '',
      nombre: state.cliente?.nombre ?? '',
      email: '',
      fe: false,
      tipo_persona: state.cliente?.tipo_persona ?? ('empresa' as const),
      tipo_identificador: state.cliente?.tipo_identificador ?? ('NIT' as const),
      apellido: state.cliente?.apellido ?? '',
    }),
    [state.cliente],
  );

  /**
   * PT-1 — "Volver" goes back EXACTLY one step, keeping everything already
   * captured (cliente, tipo de vehículo, plan, cantidad, placas, pago). On
   * step 1 it leaves the wizard (back to the list). After a successful
   * charge it does nothing: the sale is final.
   */
  const handleVolver = (): void => {
    if (ventaCompletada || isMutating) return;
    if (state.paso === 1) {
      onCancel?.();
      return;
    }
    setClienteErrors({});
    setCantidadError(null);
    setPlacasError(null);
    setPlacaGroupError(null);
    setState((s) => ({ ...s, paso: (s.paso - 1) as VentaStepState['paso'] }));
  };

  const handlePaso1Siguiente = (): void => {
    const parsed = clienteSchema.safeParse(clienteIdent);
    if (!parsed.success) {
      const fieldErrors: Partial<
        Record<'numero_identificacion' | 'dv' | 'nombre' | 'apellido', string>
      > = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as
          | 'numero_identificacion'
          | 'dv'
          | 'nombre'
          | 'apellido';
        if (!fieldErrors[key]) fieldErrors[key] = issue.message;
      }
      setClienteErrors(fieldErrors);
      return;
    }
    setClienteErrors({});
    setState((s) => ({ ...s, paso: 2, cliente: parsed.data }));
  };

  const handlePaso2Siguiente = (): void => {
    // paso 2 = Tipo de vehículo. Changing it invalidates everything that
    // depends on it (plan -> cantidad -> placas -> pago); keeping the same
    // type preserves the rest of the captured data.
    if (!tipoVehiculoInput) return;
    const changed = tipoVehiculoInput !== state.uuid_tipo_vehiculo;
    if (changed) {
      setPlanInput('');
      setCantidadInput('1');
      setPlacasInputs([]);
      setPagoDraft(null);
    }
    setState((s) => ({
      ...s,
      paso: 3,
      uuid_tipo_vehiculo: tipoVehiculoInput,
      ...(changed
        ? {
            uuid_tipo_subscripcion: undefined,
            cantidad_vehiculos: undefined,
            placas: undefined,
          }
        : {}),
    }));
  };

  const handlePaso3Siguiente = (): void => {
    // paso 3 = Plan -- validate UUID, advance to paso 4 (Cantidad).
    const parsed = planSchema.safeParse({
      uuid_tipo_subscripcion: planInput,
    });
    if (!parsed.success) {
      return;
    }
    const changed = parsed.data.uuid_tipo_subscripcion !== state.uuid_tipo_subscripcion;
    if (changed) {
      setCantidadInput('1');
      setPlacasInputs([]);
      setPagoDraft(null);
    }
    setState((s) => ({
      ...s,
      paso: 4,
      uuid_tipo_subscripcion: parsed.data.uuid_tipo_subscripcion,
      ...(changed ? { cantidad_vehiculos: undefined, placas: undefined } : {}),
    }));
  };

  const handlePaso4Siguiente = (): void => {
    // paso 4 = Cantidad -- validate 1..plan.cantidad_maxima_vehiculos,
    // advance to paso 5 (Placas) with N inputs. Already typed plates are
    // preserved by position (PT-1) when the operator comes back here.
    if (!selectedPlan) return;
    const parsed = buildCantidadSchema(selectedPlan.cantidad_maxima_vehiculos)
      .safeParse({ cantidad_vehiculos: cantidadInput });
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setCantidadError(issue?.message ?? 'invalid');
      return;
    }
    setCantidadError(null);
    const n = parsed.data.cantidad_vehiculos;
    if (n !== state.cantidad_vehiculos) setPagoDraft(null);
    setPlacasInputs((prev) => Array.from({ length: n }, (_, i) => prev[i] ?? ''));
    setPlacaGroupError(null);
    setState((s) => ({
      ...s,
      paso: 5,
      cantidad_vehiculos: n,
      fecha_inicio_cobertura: s.fecha_inicio_cobertura ?? hoyBogotaISO(),
    }));
  };

  const handlePaso5Siguiente = (): void => {
    // paso 5 = Placas -- validate exactly N placas (N from step 4), each
    // matching the auto/moto regex AND the vehicle type chosen at step 2.
    const n = state.cantidad_vehiculos ?? 1;
    const parsed = buildPlacasSchema(n).safeParse({ placas: placasInputs });
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setPlacasError(issue?.message ?? 'invalid');
      return;
    }
    const tipoNombre = (selectedTipoVehiculo?.tipo ?? '').trim().toLowerCase();
    const formatoEsperado =
      tipoNombre === 'moto' ? PLACA_MOTO : tipoNombre === 'carro' ? PLACA_AUTO : null;
    if (formatoEsperado && parsed.data.placas.some((p) => !formatoEsperado.test(p))) {
      setPlacasError('placa_tipo_incompatible');
      return;
    }
    setPlacasError(null);
    setState((s) => ({
      ...s,
      paso: 6,
      placas: parsed.data.placas,
    }));
  };

  const buildVentaPayload = (values: PagoFormValues): VentaSuscripcionCreate => {
    const fecha_inicio_cobertura =
      state.fecha_inicio_cobertura ?? hoyBogotaISO();
    // Ajuste identificación persona natural/empresa: el armado del
    // payload de cliente sale de `buildClienteVentaPayload` (función
    // pura compartida, `../lib/clienteVentaPayload.ts`).
    const clienteWizard = state.cliente ?? clienteIdent;
    const base = {
      cliente: buildClienteVentaPayload(clienteWizard),
      placas: state.placas ?? [],
      uuid_tipo_subscripcion:
        state.uuid_tipo_subscripcion ?? '',
      fecha_inicio_cobertura,
      // The FE is ALWAYS emitted by the backend. `true` bills it to the
      // subscriber (data captured at step 1); `false`/omitted bills the
      // standard customer ("consumidor final"). The checkbox of the
      // payment step only picks WHO is billed -- it no longer decides
      // whether an FE exists.
      emitir_factura_electronica: values.fe,
    };
    if (values.medio_pago === 'efectivo') {
      return {
        ...base,
        cobrar_ahora: true,
        medio_pago: 'efectivo',
      };
    }
    return {
      ...base,
      cobrar_ahora: true,
      medio_pago: 'datafono',
    };
  };

  const completeVenta = (): void => {
    if (onSuccess) {
      // Embedded consumer (F11.3 SuscripcionesSheet) -- let the
      // parent decide what happens next (close drawer, refresh
      // list, etc.). Default page-Venta consumer has no
      // `onSuccess`, so `useNavigate` runs below.
      onSuccess();
      return;
    }
    navigate('/suscripciones');
  };

  const handleFacturaDisplayClose = (): void => {
    // DEC-SUC-27 order: the recibo print fires AFTER the operator
    // dismisses the confirmation modal, same as `<PagoSheet />` /
    // `<SalidaMensualidad />`. A printer failure (offline/disconnected)
    // never blocks completing the sale (DEC-SUC-08).
    if (facturaDisplay) {
      const emit = firePrintEnvelope ?? defaultFirePrintEnvelope;
      deferredSafePrint(emit, 'recibo_pago', {
        uuid_factura: facturaDisplay.uuid,
        numero_recibo: facturaDisplay.numero_recibo,
      });
    }
    setFacturaDisplay(null);
    setFacturaElectronicaWarning(null);
    completeVenta();
  };

  const handlePagoSubmit = async (values: PagoFormValues): Promise<void> => {
    // PT-1: the sale is final once charged -- never re-send the payment.
    if (ventaCompletada) return;
    try {
      const result = await trigger(buildVentaPayload(values));
      setVentaCompletada(true);
      if (result.factura) {
        // Show the post-pago ticket/factura confirmation --
        // `completeVenta()` runs once the operator dismisses the modal.
        setFacturaDisplay(result.factura);
        setFacturaElectronicaWarning(
          feWarningMessage(
            result.factura_electronica_error ?? result.factura.factura_electronica_error,
            result.factura_electronica_pendiente ??
              result.factura.factura_electronica_pendiente,
            t,
          ),
        );
        return;
      }
      completeVenta();
    } catch (err) {
      if (
        err instanceof VentaSuscripcionDuplicatePlateError ||
        err instanceof VentaSuscripcionTipoIncompatibleError ||
        err instanceof VentaSuscripcionCantidadMaximaError
      ) {
        // Revert to the placas step (paso 5) so the operator sees which
        // input was rejected without losing the rest of the wizard state.
        const msg =
          err instanceof VentaSuscripcionDuplicatePlateError
            ? t('suscripciones:venta.errors.suscripcion_duplicada_placa', {
                defaultValue: 'Esta placa ya tiene una suscripción vigente',
              })
            : err instanceof VentaSuscripcionTipoIncompatibleError
              ? t('suscripciones:venta.errors.tipo_vehiculo_incompatible', {
                  defaultValue:
                    'Este plan exige que todas las placas sean del mismo tipo',
                })
              : t('suscripciones:venta.errors.cantidad_maxima_excedida', {
                  defaultValue: 'Cantidad máxima de vehículos excedida',
                });
        setPlacaGroupError(msg);
        setState((s) => ({ ...s, paso: 5 }));
      } else {
        throw err;
      }
    }
  };

  const mostrarVolver = !ventaCompletada && (state.paso > 1 || Boolean(onCancel));

  return (
    // F31.3 rediseño: `max-w-2xl mx-auto` — wizard centrado y acotado.
    <div className="mx-auto w-full max-w-2xl space-y-4 p-4" data-testid="venta-page">
      {/*
        PT-1: one "Volver" for the wizard whose destination depends on the
        step: step N>1 -> step N-1 (data intact); step 1 -> parent list
        (only when `onCancel` is supplied; the page route has no back
        affordance on step 1).
      */}
      {mostrarVolver && (
        <button
          type="button"
          onClick={handleVolver}
          disabled={isMutating}
          data-testid="venta-volver"
          className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50"
        >
          ← {t('suscripciones:sheet.volver', { defaultValue: 'Volver' })}
        </button>
      )}
      <header>
        <h1 className="text-xl font-semibold">
          {t('suscripciones:venta.titulo', { defaultValue: 'Venta de suscripción' })}
        </h1>
        <p className="text-xs text-muted-foreground" data-testid="venta-progreso">
          {t('suscripciones:venta.progreso', {
            paso: state.paso,
            total: TOTAL_PASOS,
            defaultValue: 'Paso {{paso}} de {{total}}',
          })}
        </p>
      </header>

      {state.paso === 1 && (
        <section className="space-y-3" data-testid="venta-paso-1">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso1.titulo', { defaultValue: 'Cliente' })}
          </h2>
          <ClienteIdentificacionFields
            testIdPrefix="venta-cliente"
            value={clienteIdent}
            onChange={(patch) => setClienteIdent((prev) => ({ ...prev, ...patch }))}
            errors={clienteErrors}
          />
          <Button
            type="button"
            data-testid="venta-paso-1-siguiente"
            onClick={handlePaso1Siguiente}
          >
            {t('suscripciones:venta.siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </section>
      )}

      {state.paso === 2 && (
        <section className="space-y-3" data-testid="venta-paso-2">
          <h2 className="text-lg" id="venta-paso-2-titulo">
            {t('suscripciones:venta.paso2.titulo', { defaultValue: 'Tipo de vehículo' })}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('suscripciones:venta.paso2.descripcion', {
              defaultValue: 'Elegí el tipo de vehículo: solo verás los planes que le corresponden.',
            })}
          </p>
          {tiposFromFallback && (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="venta-paso-2-tipos-error"
            >
              {t('suscripciones:venta.paso2.tiposError', {
                defaultValue: 'No se pudo cargar el catálogo de tipos de vehículo. Intentá de nuevo.',
              })}
            </p>
          )}
          {!tiposFromFallback && (
            <div
              role="radiogroup"
              aria-labelledby="venta-paso-2-titulo"
              className="grid grid-cols-2 gap-2"
              data-testid="venta-paso-2-tipos"
            >
              {tiposVehiculo.map((tv) => {
                const selected = tipoVehiculoInput === tv.uuid;
                return (
                  <button
                    key={tv.uuid}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    data-testid={`venta-tipo-vehiculo-${tv.uuid}`}
                    onClick={() => setTipoVehiculoInput(tv.uuid)}
                    className={
                      'rounded border p-3 text-sm font-medium capitalize transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
                      (selected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50')
                    }
                  >
                    {tv.tipo}
                  </button>
                );
              })}
            </div>
          )}
          <Button
            type="button"
            data-testid="venta-paso-2-siguiente"
            onClick={handlePaso2Siguiente}
            disabled={!tipoVehiculoInput}
          >
            {t('suscripciones:venta.siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </section>
      )}

      {state.paso === 3 && (
        <section className="space-y-3" data-testid="venta-paso-3">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso3.titulo', { defaultValue: 'Plan' })}
          </h2>
          {selectedTipoVehiculo && (
            <p className="text-xs text-muted-foreground" data-testid="venta-paso-3-tipo">
              {t('suscripciones:venta.paso3.tipoElegido', {
                tipo: selectedTipoVehiculo.tipo,
                defaultValue: 'Planes para: {{tipo}}',
              })}
            </p>
          )}

          {/*
            Plan catalog from `GET /api/v1/catalogos/tipo-subscripciones`
            filtered by the vehicle type picked at step 2 (the backend adds
            the plans valid for any type). The selected plan's
            `cantidad_maxima_vehiculos` caps the next step's quantity input.
          */}
          {planesLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="venta-paso-3-loading"
            >
              {t('suscripciones:venta.paso3.loading', {
                defaultValue: 'Cargando planes…',
              })}
            </p>
          )}
          {planesError && (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="venta-paso-3-error"
            >
              {t('suscripciones:venta.paso3.error', {
                defaultValue:
                  'No se pudieron cargar los planes para esta sede.',
              })}
            </p>
          )}
          {planes && planes.length === 0 && !planesLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="venta-paso-3-empty"
            >
              {t('suscripciones:venta.paso3.empty', {
                defaultValue: 'No hay planes configurados para este tipo de vehículo en esta sede.',
              })}
            </p>
          )}
          {planes && planes.length > 0 && (
            <ul
              className="space-y-2"
              data-testid="venta-paso-3-planes"
            >
              {planes.map((p) => {
                const selected = planInput === p.uuid;
                return (
                  <li
                    key={p.uuid}
                    data-testid={`venta-plan-${p.uuid}`}
                    onClick={() => setPlanInput(p.uuid)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setPlanInput(p.uuid);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    aria-pressed={selected}
                    className={
                      'cursor-pointer rounded border p-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ' +
                      (selected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50')
                    }
                  >
                    <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
                      <div className="min-w-0 flex-1">
                        <div className="break-words font-medium">{p.tipo}</div>
                        <div className="break-words text-xs text-muted-foreground">
                          {t('suscripciones:venta.paso3.duracion', {
                            dias: p.duracion_dias,
                            vehiculos: p.cantidad_maxima_vehiculos,
                            defaultValue: `{{dias}} días · máx {{vehiculos}} vehículo(s)`,
                          })}
                        </div>
                      </div>
                      <div
                        className="shrink-0 font-medium tabular-nums"
                        data-testid={`venta-plan-${p.uuid}-valor`}
                      >
                        {formatCOP(p.valor)}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <Button
            type="button"
            data-testid="venta-paso-3-siguiente"
            onClick={handlePaso3Siguiente}
            disabled={!planInput}
          >
            {t('suscripciones:venta.siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </section>
      )}

      {state.paso === 4 && (
        <section className="space-y-3" data-testid="venta-paso-4">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso4.titulo', {
              defaultValue: 'Cantidad de vehículos',
            })}
          </h2>
          <p className="text-sm text-muted-foreground">
            {selectedPlan
              ? t('suscripciones:venta.paso4.descripcion', {
                  max: selectedPlan.cantidad_maxima_vehiculos,
                  defaultValue: `Este plan permite hasta ${selectedPlan.cantidad_maxima_vehiculos} vehículo(s). ¿Cuántos vas a registrar?`,
                })
              : null}
          </p>
          <label className="sr-only" htmlFor="venta-cantidad-input">
            {t('suscripciones:venta.paso4.titulo', {
              defaultValue: 'Cantidad de vehículos',
            })}
          </label>
          <Input
            id="venta-cantidad-input"
            type="text"
            inputMode="decimal"
            data-testid="venta-cantidad-input"
            value={cantidadInput}
            onChange={(e) => {
              const raw = e.target.value;
              // Numeric input regex: empty or 1..max digits.
              if (raw === '' || /^\d+$/.test(raw)) {
                setCantidadInput(raw);
                setCantidadError(null);
              }
            }}
            placeholder="1"
          />
          {cantidadError && (
            <span
              data-testid="venta-cantidad-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {cantidadError}
            </span>
          )}
          <Button
            type="button"
            data-testid="venta-paso-4-siguiente"
            onClick={handlePaso4Siguiente}
            disabled={cantidadInput === '' || !selectedPlan}
          >
            {t('suscripciones:venta.siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </section>
      )}

      {state.paso === 5 && (
        <section className="space-y-3" data-testid="venta-paso-5">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso5.titulo', { defaultValue: 'Placas' })}
          </h2>
          {placaGroupError && (
            <p
              data-testid="venta-placas-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {placaGroupError}
            </p>
          )}
          <div className="space-y-2" data-testid="venta-placas-list">
            {placasInputs.map((placa, i) => (
              <div key={i} className="space-y-1">
                <label
                  className="text-xs text-muted-foreground"
                  htmlFor={`venta-placa-input-${i}`}
                >
                  {t('suscripciones:venta.paso5.vehiculoLabel', {
                    n: i + 1,
                    defaultValue: `Vehículo ${i + 1}`,
                  })}
                </label>
                <Input
                  id={`venta-placa-input-${i}`}
                  type="text"
                  data-testid={`venta-placa-input-${i}`}
                  value={placa}
                  maxLength={6}
                  autoCapitalize="characters"
                  onChange={(e) => {
                    const raw = e.target.value.toUpperCase();
                    // Mirror the turnoSchema regex: keep only valid
                    // placa chars so the field never enters a state
                    // the schema would reject.
                    if (raw === '' || /^[A-Z0-9]{0,6}$/.test(raw)) {
                      setPlacasInputs((arr) => {
                        const next = arr.slice();
                        next[i] = raw;
                        return next;
                      });
                      setPlacasError(null);
                    }
                  }}
                  placeholder="ABC123"
                />
              </div>
            ))}
          </div>
          {placasError && (
            <span
              data-testid="venta-placas-format-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {placasError === 'placa_tipo_incompatible'
                ? t('suscripciones:venta.errors.placa_tipo_incompatible', {
                    tipo: selectedTipoVehiculo?.tipo ?? '',
                    defaultValue: `La placa no corresponde al tipo de vehículo elegido (${selectedTipoVehiculo?.tipo ?? ''}).`,
                  })
                : placasError}
            </span>
          )}
          <Button
            type="button"
            data-testid="venta-paso-5-siguiente"
            onClick={handlePaso5Siguiente}
            disabled={placasInputs.some((p) => p === '')}
          >
            {t('suscripciones:venta.siguiente', { defaultValue: 'Siguiente' })}
          </Button>
        </section>
      )}

      {state.paso === 6 && !ventaCompletada && (
        <section className="space-y-3" data-testid="venta-paso-6">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso6.titulo', { defaultValue: 'Pago' })}
          </h2>
          {/*
            PagoModal composition (REQ-OPS-180): reuses F8.1 `<PagoModal />`.
            `clientePrefill` carries the step-1 cliente; `identificacionReadonly`
            because `buildVentaPayload` builds `cliente` ONLY from step 1.
            `draft`/`onDraftChange` (PT-1) keep what the operator typed (medio
            de pago, monto, voucher, ...) when stepping back and returning.
            The FE is always emitted: the checkbox only chooses to bill the
            subscriber instead of "consumidor final".
          */}
          <PagoModal
            uuid_ingreso={null}
            total_cop={selectedPlan?.valor ?? PLAN_PREVIEW_VALOR}
            clientePrefill={clientePrefill}
            identificacionReadonly
            draft={pagoDraft}
            onDraftChange={setPagoDraft}
            feCheckboxLabel={t('suscripciones:venta.paso6.feSuscriptor', {
              defaultValue: 'Facturar a nombre del suscriptor (opcional)',
            })}
            onSubmit={handlePagoSubmit}
          />
          {isMutating && <span data-testid="venta-mutating">Procesando…</span>}
        </section>
      )}
      {/*
        Post-pago confirmation -- full breakdown (mirrors HU-F8.4
        `<FacturaDisplayModal />`) and the recibo print on dismiss. Mounted
        unconditionally so the close animation plays; renders nothing while
        `facturaDisplay` is `null`. Shows the FE state (emitted / pending).
      */}
      <FacturaDisplayModal
        factura={facturaDisplay}
        onClose={handleFacturaDisplayClose}
        warning={facturaElectronicaWarning}
      />
    </div>
  );
}
