/**
 * `<Venta />` — F9.1 wizard 4 pasos for subscription sale at the
 * counter (HU-F9.1, REQ-OPS-176).
 *
 * Layout (REQ-OPS-176 verbatim):
 *   paso 1 — cliente{tipo_persona, tipo_identificador, numero_identificacion,
 *             dv?, nombre, apellido?} (Ajuste persona natural/empresa:
 *             `<ClienteIdentificacionFields>`, mismo componente compartido
 *             que `<PagoModal>` paso 5)
 *   paso 2 — placas[] (1..2, FORMATO_AUTO | FORMATATO_MOTO)
 *   paso 3 — uuid_tipo_subscripcion (UUID)
 *   paso 4 — `<PagoModal />` (F8.1 reuse) — F8.1 owns vueltos live
 *             + FE con datos + NIT módulo 11 validation
 *
 * State machine: `useState<VentaStepState>` orchestrating the 4
 * steps. Each step has its own Zod schema; advancing triggers
 * `safeParse` BEFORE `setPaso(paso + 1)`. This matches F7.1/F7.2/
 * F8.1 patterns (per-step validation, NOT a single big schema at
 * submit time) and keeps each step's error rendering local.
 *
 * Step 2 catches the 3 backend 422 error subclasses
 * (`VentaSuscripcionDuplicatePlateError`,
 * `VentaSuscripcionTipoIncompatibleError`,
 * `VentaSuscripcionCantidadMaximaError`) and renders the inline
 * message with `instanceof` discrimination.
 *
 * Step 4 displays "Monto prorrateado: $X" badge when
 * `calcularMontoProporcional(plan, fecha) !== null` (A-09 +
 * DEC-VENTA-03). The PagoModal receives `total_cop = monto_prorrateado
 * ?? plan.valor` so vueltos live reflects the actual charge.
 *
 * On pago 201 the wizard navigates to `/suscripciones` (F9.2 list).
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
import { calcularMontoProporcional } from '../lib/prorrateo';
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

/**
 * KD-VENTA-03b — maps the backend's `factura_electronica_error` code to
 * an operator-facing message. `null` when the sale had no FE issue.
 * Kept as a plain function (not a hook) so it can be called from the
 * `handlePagoSubmit` closure without an extra `useCallback`.
 */
function facturaElectronicaErrorMessage(
  code: string | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  if (!code) return null;
  switch (code) {
    case 'resolucion_facturacion_no_encontrada':
      return t('suscripciones:venta.fe.resolucionNoEncontrada', {
        defaultValue:
          'El cobro y la suscripción quedaron registrados, pero no se pudo emitir la factura electrónica: falta configurar la resolución de facturación de esta sucursal.',
      });
    case 'numeracion_agotada':
      return t('suscripciones:venta.fe.numeracionAgotada', {
        defaultValue:
          'El cobro y la suscripción quedaron registrados, pero se agotó la numeración de la resolución de facturación. Avisá para renovarla.',
      });
    case 'resolucion_sin_prefijo':
      return t('suscripciones:venta.fe.resolucionSinPrefijo', {
        defaultValue:
          'El cobro y la suscripción quedaron registrados, pero la resolución de facturación no tiene prefijo configurado.',
      });
    default:
      return t('suscripciones:venta.fe.errorGenerico', {
        defaultValue:
          'El cobro y la suscripción quedaron registrados, pero no se pudo emitir la factura electrónica. Reintentalo más tarde.',
      });
  }
}

export interface VentaStepState {
  paso: 1 | 2 | 3 | 4 | 5;
  cliente?: ClienteIdentificacionValue;
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
 * Default plan valor / duracion_dias used for the prorrateo
 * display when the operator hasn't selected a plan yet (early
 * render of step 4). When a plan IS selected, its `valor` and
 * `duracion_dias` drive the prorrateo computation. The authoritative
 * amount is still computed server-side at the POST (defense in
 * depth -- the wizard's preview is informational).
 */
const PLAN_PREVIEW_VALOR = 30000;
const PLAN_PREVIEW_DURACION_DIAS = 30;

const DEFAULT_FECHA_INICIO = '2026-09-19'; // day=19 → prorrateo visible

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
  const [planInput, setPlanInput] = useState('');
  const [cantidadError, setCantidadError] = useState<string | null>(null);
  const [cantidadInput, setCantidadInput] = useState('1');
  const [placasError, setPlacasError] = useState<string | null>(null);
  // Per-placa input draft state. Length matches state.placas when
  // step 4 is mounted. Initialised empty when the operator advances
  // from paso 3 with N cantidad.
  const [placasInputs, setPlacasInputs] = useState<string[]>([]);
  // Generic inline error for step 4 -- shared by both duplicate-plate
  // 422 (server response) and invalid-format (local Zod). The error
  // attribute is shown under the placa input group; the specific
  // input that triggered the error is highlighted by the server's
  // own discriminated error message (VentaSuscripcionDuplicatePlateError).
  const [placaGroupError, setPlacaGroupError] = useState<string | null>(null);
  // HU-F9.1 bugfix (2026-09-25): hold the enriched `FacturaRead` the
  // backend now returns when `cobrar_ahora=true` so we can mount
  // `<FacturaDisplayModal />` with the full breakdown before completing
  // the wizard -- mirrors HU-F8.4 (ingreso/salida cobro flow). Previously
  // the wizard navigated away immediately after a paid sale with no
  // ticket/factura confirmation shown to the operator.
  const [facturaDisplay, setFacturaDisplay] = useState<FacturaRead | null>(null);
  // KD-VENTA-03b (operator directive, 2026-09-25): FE emission is
  // best-effort and runs AFTER the payment already committed -- a
  // non-null `factura_electronica_error` means the sale + factura
  // succeeded but the electronic invoice didn't. Shown as a
  // non-blocking warning inside the same confirmation modal instead of
  // silently dropping it.
  const [facturaElectronicaWarning, setFacturaElectronicaWarning] = useState<
    string | null
  >(null);
  const { trigger, isMutating } = useVentaSuscripcion();
  const {
    data: planes,
    error: planesError,
    isLoading: planesLoading,
  } = useTiposSubscripciones(uuid_sucursal);

  // Look up the selected plan's pricing once the operator commits to
  // a uuid_tipo_subscripcion at step 3. Used by step 4 to render the
  // prorrateo badge against the canonical plan numbers instead of
  // the F9.1-era 30000/30 preview baseline.
  const selectedPlan = useMemo(() => {
    if (!planes || !state.uuid_tipo_subscripcion) return null;
    return (
      planes.find((p) => p.uuid === state.uuid_tipo_subscripcion) ?? null
    );
  }, [planes, state.uuid_tipo_subscripcion]);

  const montoProporcional = useMemo<number | null>(() => {
    if (state.paso !== 5 || !state.fecha_inicio_cobertura) return null;
    const planArgs = selectedPlan
      ? {
          valor: selectedPlan.valor,
          duracion_dias: selectedPlan.duracion_dias,
        }
      : { valor: PLAN_PREVIEW_VALOR, duracion_dias: PLAN_PREVIEW_DURACION_DIAS };
    return calcularMontoProporcional(planArgs, new Date(state.fecha_inicio_cobertura));
  }, [state.paso, state.fecha_inicio_cobertura, selectedPlan]);

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
    // paso 2 = Plan -- validate UUID, advance to paso 3 (Cantidad).
    const parsed = planSchema.safeParse({
      uuid_tipo_subscripcion: planInput,
    });
    if (!parsed.success) {
      return;
    }
    setState((s) => ({
      ...s,
      paso: 3,
      uuid_tipo_subscripcion: parsed.data.uuid_tipo_subscripcion,
    }));
  };

  const handlePaso3Siguiente = (): void => {
    // paso 3 = Cantidad -- validate 1..plan.cantidad_maxima_vehiculos,
    // advance to paso 4 (Placas) with a pre-allocated array of N
    // empty strings so the placa inputs are immediately mounted.
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
    setPlacasInputs(new Array(n).fill(''));
    setPlacaGroupError(null);
    setState((s) => ({
      ...s,
      paso: 4,
      cantidad_vehiculos: n,
      placas: new Array(n).fill(''),
      fecha_inicio_cobertura: DEFAULT_FECHA_INICIO,
    }));
  };

  const handlePaso4Siguiente = (): void => {
    // paso 4 = Placas -- validate exactly N placas (N from step 3),
    // each matching the auto/moto regex. Advance to paso 5 (Pago).
    const n = state.cantidad_vehiculos ?? 1;
    const parsed = buildPlacasSchema(n).safeParse({ placas: placasInputs });
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setPlacasError(issue?.message ?? 'invalid');
      return;
    }
    setPlacasError(null);
    setState((s) => ({
      ...s,
      paso: 5,
      placas: parsed.data.placas,
    }));
  };

  const buildVentaPayload = (values: PagoFormValues): VentaSuscripcionCreate => {
    const fecha_inicio_cobertura =
      state.fecha_inicio_cobertura ?? DEFAULT_FECHA_INICIO;
    // Ajuste identificación persona natural/empresa: el armado del
    // payload de cliente sale de `buildClienteVentaPayload` (función
    // pura compartida, `../lib/clienteVentaPayload.ts`) — ya NO se
    // hardcodea `tipo_identificador: 'NIT'` acá.
    const clienteWizard = state.cliente ?? clienteIdent;
    const base = {
      cliente: buildClienteVentaPayload(clienteWizard),
      placas: state.placas ?? [],
      uuid_tipo_subscripcion:
        state.uuid_tipo_subscripcion ?? '',
      fecha_inicio_cobertura,
      // Genera FE con los datos del cliente del paso 1 -- el toggle
      // `fe` de PagoModal lo controla en tiempo real. Plan.md §6.2
      // (F11.3 follow-up) requiere que el `cliente` payload viaje
      // completo para que el backend pueda emitir la FE sin re-
      // preguntarle al operador.
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
    try {
      const result = await trigger(buildVentaPayload(values));
      if (result.factura) {
        // HU-F9.1 bugfix: show the post-pago ticket/factura
        // confirmation instead of silently navigating away --
        // `completeVenta()` runs once the operator dismisses the
        // modal (`handleFacturaDisplayClose`).
        setFacturaDisplay(result.factura);
        setFacturaElectronicaWarning(
          facturaElectronicaErrorMessage(result.factura_electronica_error, t),
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
        // F11.3 follow-up: revert to paso 4 (Placas) so the operator
        // sees which input was rejected without losing the rest of
        // the wizard state. For DuplicatePlateError we also highlight
        // the offending plate position when the server includes it
        // (today the error is generic; ABBC-F11.3-1 future work).
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
        setState((s) => ({ ...s, paso: 4 }));
      } else {
        throw err;
      }
    }
  };

  return (
    // F31.3 rediseño: `max-w-2xl mx-auto` — el wizard de 4 pasos
    // (inputs cortos, cards de plan) se estiraba a todo el ancho en
    // 4K/ultrawide/21:9. Centrado + acotado se ve bien tanto standalone
    // (ruta `/suscripciones/venta`) como embebido en `<SuscripcionesSheet>`
    // (que ya acota su propio ancho — este max-w solo angosta más la
    // columna del wizard dentro de ese panel, no compite con él).
    <div className="mx-auto w-full max-w-2xl space-y-4 p-4" data-testid="venta-page">
      {/*
        Embedded-wizard "Volver" button (visible only when `onCancel`
        is supplied). Clicking returns the parent to its list view
        without unmounting Venta's state (the parent uses conditional
        render). For page-Venta (no onCancel), no back affordance --
        the operator navigates back via the browser or sidebar.
      */}
      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          data-testid="venta-volver"
          className="inline-flex items-center gap-1 rounded-sm text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          ← {t('suscripciones:sheet.volver', { defaultValue: 'Volver' })}
        </button>
      )}
      <header>
        <h1 className="text-xl font-semibold">
          {t('suscripciones:venta.titulo', { defaultValue: 'Venta de suscripción' })}
        </h1>
      </header>
      {/*
        PagoModal composition (REQ-OPS-180, OD-2 ratified):
        step 4 reuses F8.1 `<PagoModal />` from
        `../../facturacion/components/PagoModal`. PagoModal owns
        vueltos live + FE con datos + NIT módulo 11 validation —
        no duplicate UI in the wizard. `total_cop = monto_proporcional
        ?? plan.valor` so vueltos live reflects the actual charge
        (informational; authoritative amount is `factura_detalle.valor_unitario`).
        On pago 201, `handlePagoSubmit` calls `trigger` + navigates
        to `/suscripciones` (F9.2 list).
      */}

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
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 2 && (
        <section className="space-y-3" data-testid="venta-paso-2">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso2.titulo', { defaultValue: 'Plan' })}
          </h2>

          {/*
            Plan catalog from `GET /api/v1/catalogos/tipo-subscripciones`.
            Operator picks the plan they want to subscribe to -- the
            selected plan's `uuid` flows into
            `state.uuid_tipo_subscripcion` and its
            `cantidad_maxima_vehiculos` caps the next step's quantity
            input. The full valor + duracion_dias drive the prorrateo
            badge in step 5.
          */}
          {planesLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="venta-paso-2-loading"
            >
              {t('suscripciones:venta.paso2.loading', {
                defaultValue: 'Cargando planes…',
              })}
            </p>
          )}
          {planesError && (
            <p
              role="alert"
              className="text-sm text-destructive"
              data-testid="venta-paso-2-error"
            >
              {t('suscripciones:venta.paso2.error', {
                defaultValue:
                  'No se pudieron cargar los planes para esta sede.',
              })}
            </p>
          )}
          {planes && planes.length === 0 && !planesLoading && (
            <p
              className="text-sm text-muted-foreground"
              data-testid="venta-paso-2-empty"
            >
              {t('suscripciones:venta.paso2.empty', {
                defaultValue: 'No hay planes configurados para esta sede.',
              })}
            </p>
          )}
          {planes && planes.length > 0 && (
            <ul
              className="space-y-2"
              data-testid="venta-paso-2-planes"
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
                          {t('suscripciones:venta.paso2.duracion', {
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
            data-testid="venta-paso-2-siguiente"
            onClick={handlePaso2Siguiente}
            disabled={!planInput}
          >
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 3 && (
        <section className="space-y-3" data-testid="venta-paso-3">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso3.titulo', {
              defaultValue: 'Cantidad de vehículos',
            })}
          </h2>
          <p className="text-sm text-muted-foreground">
            {selectedPlan
              ? t('suscripciones:venta.paso3.descripcion', {
                  max: selectedPlan.cantidad_maxima_vehiculos,
                  defaultValue: `Este plan permite hasta ${selectedPlan.cantidad_maxima_vehiculos} vehículo(s). ¿Cuántos vas a registrar?`,
                })
              : null}
          </p>
          <Input
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
            data-testid="venta-paso-3-siguiente"
            onClick={handlePaso3Siguiente}
            disabled={cantidadInput === ''}
          >
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 4 && (
        <section className="space-y-3" data-testid="venta-paso-4">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso4.titulo', { defaultValue: 'Placas' })}
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
                  {t('suscripciones:venta.paso4.vehiculoLabel', {
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
              {placasError}
            </span>
          )}
          <Button
            type="button"
            data-testid="venta-paso-4-siguiente"
            onClick={handlePaso4Siguiente}
            disabled={placasInputs.some((p) => p === '')}
          >
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 5 && (
        <section className="space-y-3" data-testid="venta-paso-5">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso5.titulo', { defaultValue: 'Pago' })}
          </h2>
          {montoProporcional !== null && (
            <p
              data-testid="venta-prorrateo-badge"
              className="text-sm bg-muted px-2 py-1 inline-block rounded"
            >
              {t('suscripciones:venta.prorrateo.label', {
                defaultValue: 'Monto prorrateado',
              })}
              : {formatCOP(montoProporcional)}
            </p>
          )}
          {/*
            PagoModal composition (REQ-OPS-180, OD-2 ratified):
            step 5 reuses F8.1 `<PagoModal />` from
            `../../facturacion/components/PagoModal`. PagoModal owns
            vueltos live + FE con datos + NIT módulo 11 validation.
            `clientePrefill` carries step-1 tipo_persona/tipo_identificador/
            numero/nombre/apellido into the PagoModal form. `fe: true`
            flips the "Generar factura
            electrónica" toggle ON at step 5 entry -- operator can
            still untick for a no-FE sale. `total_cop =
            monto_proporcional ?? plan.valor` so vueltos live
            reflects the actual charge (informational; authoritative
            amount is `factura_detalle.valor_unitario`). On pago 201,
            `handlePagoSubmit` calls `trigger` with
            `emitir_factura_electronica: values.fe` and either
            navigates to /suscripciones (page route) or fires the
            parent's `onSuccess` (embedded drawer).

            `identificacionReadonly` (fix 2026-09-25, decisión del
            operador): `buildVentaPayload` arma `cliente` EXCLUSIVAMENTE
            desde `state.cliente` (paso 1) -- el bloque de identificación
            que `<PagoModal>` muestra acá es puramente decorativo, así
            que se deshabilita (valores fijados por `clientePrefill`) en
            vez de dejarlo editable y bloquear el submit con una
            validación de DV sobre un valor que después se descarta.
          */}
          <PagoModal
            uuid_ingreso={null}
            total_cop={
              montoProporcional ??
              (selectedPlan?.valor ?? PLAN_PREVIEW_VALOR)
            }
            clientePrefill={{
              nit: state.cliente?.numero_identificacion ?? '',
              nombre: state.cliente?.nombre ?? '',
              email: '',
              fe: true,
              tipo_persona: state.cliente?.tipo_persona ?? 'empresa',
              tipo_identificador: state.cliente?.tipo_identificador ?? 'NIT',
              apellido: state.cliente?.apellido ?? '',
            }}
            identificacionReadonly
            onSubmit={handlePagoSubmit}
          />
          {isMutating && <span data-testid="venta-mutating">Procesando…</span>}
        </section>
      )}
      {/*
        HU-F9.1 bugfix (2026-09-25): post-pago confirmation -- shows the
        full breakdown (mirrors HU-F8.4 `<FacturaDisplayModal />`) and
        fires the recibo print envelope on dismiss. Mounted unconditionally
        (like `<SalidaMensualidad />`'s copy) so the close animation plays;
        it renders nothing while `facturaDisplay` is `null`.
      */}
      <FacturaDisplayModal
        factura={facturaDisplay}
        onClose={handleFacturaDisplayClose}
        warning={facturaElectronicaWarning}
      />
    </div>
  );
}
