/**
 * `<Venta />` — F9.1 wizard 4 pasos for subscription sale at the
 * counter (HU-F9.1, REQ-OPS-176).
 *
 * Layout (REQ-OPS-176 verbatim):
 *   paso 1 — cliente{nit, nombre, email}
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

import {
  useVentaSuscripcion,
  VentaSuscripcionDuplicatePlateError,
  VentaSuscripcionTipoIncompatibleError,
  VentaSuscripcionCantidadMaximaError,
  type VentaSuscripcionCreate,
} from '../hooks/useVentaSuscripcion';
import { useTiposSubscripciones } from '../hooks/useTiposSubscripciones';
import { calcularMontoProporcional } from '../lib/prorrateo';

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
 */
export interface VentaProps {
  onSuccess?: () => void;
  onCancel?: () => void;
}

export interface VentaStepState {
  paso: 1 | 2 | 3 | 4;
  cliente?: { nit: string; nombre: string; email: string | null };
  placas?: string[];
  uuid_tipo_subscripcion?: string;
  fecha_inicio_cobertura?: string;
  monto_proporcional?: number | null;
}

// Per-step Zod schemas — mirrors F8.1 PagoModal discriminated union.
const clienteSchema = z.object({
  nit: z.string().min(6, 'nit_min_6'),
  nombre: z.string().min(1, 'nombre_requerido'),
  email: z
    .string()
    .email('email_formato_invalido')
    .nullable()
    .optional(),
});

const placasSchema = z.object({
  placas: z
    .array(
      z
        .string()
        .regex(
          /^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/,
          'placa_formato_invalido',
        ),
    )
    .min(1, 'placas_min_1')
    .max(2, 'placas_max_2'),
});

const planSchema = z.object({
  uuid_tipo_subscripcion: z
    .string()
    .uuid('uuid_tipo_subscripcion_invalido'),
  fecha_inicio_cobertura: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
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

export function Venta({ onSuccess, onCancel }: VentaProps = {}): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const navigate = useNavigate();
  const { sucursal } = useAuth();
  const uuid_sucursal = sucursal?.uuid ?? null;
  const [state, setState] = useState<VentaStepState>({ paso: 1 });
  const [placaError, setPlacaError] = useState<string | null>(null);
  const [clienteError, setClienteError] = useState<string | null>(null);
  const [clienteNitInput, setClienteNitInput] = useState('');
  const [clienteNombreInput, setClienteNombreInput] = useState('');
  const [placaInput, setPlacaInput] = useState('');
  const [planInput, setPlanInput] = useState('');
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
    if (state.paso !== 4 || !state.fecha_inicio_cobertura) return null;
    const planArgs = selectedPlan
      ? {
          valor: selectedPlan.valor,
          duracion_dias: selectedPlan.duracion_dias,
        }
      : { valor: PLAN_PREVIEW_VALOR, duracion_dias: PLAN_PREVIEW_DURACION_DIAS };
    return calcularMontoProporcional(planArgs, new Date(state.fecha_inicio_cobertura));
  }, [state.paso, state.fecha_inicio_cobertura, selectedPlan]);

  const handlePaso1Siguiente = (): void => {
    const parsed = clienteSchema.safeParse({
      nit: clienteNitInput,
      nombre: clienteNombreInput,
      email: null,
    });
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      setClienteError(issue?.message ?? 'invalid');
      return;
    }
    setClienteError(null);
    setState((s) => ({ ...s, paso: 2, cliente: parsed.data }));
  };

  const handlePaso2Siguiente = (): void => {
    const parsed = placasSchema.safeParse({ placas: [placaInput] });
    if (!parsed.success) {
      setPlacaError('placa_formato_invalido');
      return;
    }
    setPlacaError(null);
    setState((s) => ({
      ...s,
      paso: 3,
      placas: parsed.data.placas,
      fecha_inicio_cobertura: DEFAULT_FECHA_INICIO,
    }));
  };

  const handlePaso3Siguiente = (): void => {
    const parsed = planSchema.safeParse({
      uuid_tipo_subscripcion: planInput,
      fecha_inicio_cobertura: DEFAULT_FECHA_INICIO,
    });
    if (!parsed.success) {
      return;
    }
    setState((s) => ({
      ...s,
      paso: 4,
      uuid_tipo_subscripcion: parsed.data.uuid_tipo_subscripcion,
    }));
  };

  const buildVentaPayload = (values: PagoFormValues): VentaSuscripcionCreate => {
    const fecha_inicio_cobertura =
      state.fecha_inicio_cobertura ?? DEFAULT_FECHA_INICIO;
    const base = {
      cliente: state.cliente ?? { nit: '', nombre: '', email: null },
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

  const handlePagoSubmit = async (values: PagoFormValues): Promise<void> => {
    try {
      await trigger(buildVentaPayload(values));
      if (onSuccess) {
        // Embedded consumer (F11.3 SuscripcionesSheet) -- let the
        // parent decide what happens next (close drawer, refresh
        // list, etc.). Default page-Venta consumer has no
        // `onSuccess`, so `useNavigate` runs below.
        onSuccess();
        return;
      }
      navigate('/suscripciones');
    } catch (err) {
      if (
        err instanceof VentaSuscripcionDuplicatePlateError ||
        err instanceof VentaSuscripcionTipoIncompatibleError ||
        err instanceof VentaSuscripcionCantidadMaximaError
      ) {
        // Map to step 2 inline error and revert to paso 2.
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
        setPlacaError(msg);
        setState((s) => ({ ...s, paso: 2 }));
      } else {
        throw err;
      }
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="venta-page">
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
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
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
          <Input
            data-testid="venta-cliente-nit"
            placeholder="NIT"
            value={clienteNitInput}
            onChange={(e) => setClienteNitInput(e.target.value)}
          />
          {clienteError && (
            <span
              data-testid="venta-cliente-nit-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {clienteError}
            </span>
          )}
          <Input
            data-testid="venta-cliente-nombre"
            placeholder="Nombre"
            value={clienteNombreInput}
            onChange={(e) => setClienteNombreInput(e.target.value)}
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
            {t('suscripciones:venta.paso2.titulo', { defaultValue: 'Vehículos' })}
          </h2>
          <Input
            data-testid="venta-placa-input"
            placeholder="Placa"
            value={placaInput}
            onChange={(e) => setPlacaInput(e.target.value)}
          />
          {placaError && (
            <p
              data-testid="venta-placa-error"
              className="text-sm text-destructive"
              role="alert"
            >
              {placaError}
            </p>
          )}
          <Button
            type="button"
            data-testid="venta-paso-2-siguiente"
            onClick={handlePaso2Siguiente}
          >
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 3 && (
        <section className="space-y-3" data-testid="venta-paso-3">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso3.titulo', { defaultValue: 'Plan' })}
          </h2>

          {/*
            Plan catalog from `GET /api/v1/tipos-subscripciones`. The
            operator picks the plan they want to subscribe to --
            no more typing the plan's UUID by hand. The selected
            plan's `uuid` flows into `state.uuid_tipo_subscripcion`
            and from there into the POST body via buildVentaPayload.
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
                defaultValue: 'No hay planes configurados para esta sede.',
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
                      'cursor-pointer rounded border p-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring ' +
                      (selected
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:bg-muted/50')
                    }
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="font-medium">{p.tipo}</div>
                        <div className="text-xs text-muted-foreground">
                          {t('suscripciones:venta.paso3.duracion', {
                            dias: p.duracion_dias,
                            vehiculos: p.cantidad_maxima_vehiculos,
                            defaultValue: `{{dias}} días · máx {{vehiculos}} vehículo(s)`,
                          })}
                        </div>
                      </div>
                      <div
                        className="font-medium tabular-nums"
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
            Siguiente
          </Button>
        </section>
      )}

      {state.paso === 4 && (
        <section className="space-y-3" data-testid="venta-paso-4">
          <h2 className="text-lg">
            {t('suscripciones:venta.paso4.titulo', { defaultValue: 'Pago' })}
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
            step 4 reuses F8.1 `<PagoModal />` from
            `../../facturacion/components/PagoModal`. PagoModal owns
            vueltos live + FE con datos + NIT módulo 11 validation.
            `clientePrefill` carries step-1 NIT/nombre/email into the
            PagoModal form (instead of the consumidor final fallback
            the page route uses by default). `fe: true` flips the
            "Generar factura electrónica" toggle ON as soon as the
            wizard reaches step 4 -- the operator can still untick
            it if they explicitly want a no-FE sale. `total_cop =
            monto_proporcional ?? plan.valor` so vueltos live
            reflects the actual charge (informational; the
            authoritative amount is `factura_detalle.valor_unitario`).
            On pago 201, `handlePagoSubmit` calls `trigger` with the
            `emitir_factura_electronica` from `values.fe` and either
            navigates to /suscripciones (page route) or fires the
            parent's `onSuccess` (embedded drawer).
          */}
          <PagoModal
            uuid_ingreso={null}
            total_cop={
              montoProporcional ??
              (selectedPlan?.valor ?? PLAN_PREVIEW_VALOR)
            }
            clientePrefill={{
              nit: state.cliente?.nit ?? '',
              nombre: state.cliente?.nombre ?? '',
              email: state.cliente?.email ?? '',
              fe: true,
            }}
            onSubmit={handlePagoSubmit}
          />
          {isMutating && <span data-testid="venta-mutating">Procesando…</span>}
        </section>
      )}
    </div>
  );
}
