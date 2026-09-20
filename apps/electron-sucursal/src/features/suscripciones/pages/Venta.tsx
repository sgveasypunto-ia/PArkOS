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
import { calcularMontoProporcional } from '../lib/prorrateo';

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
 * display. In a full integration the wizard would resolve this from
 * the plan catalog (`useTiposSubscripcion`); for F9.1 the wizard
 * reads the plan from the step 3 select and uses a 30/30 baseline
 * for the badge preview. The authoritative amount is computed
 * server-side at the POST.
 */
const PLAN_PREVIEW_VALOR = 30000;
const PLAN_PREVIEW_DURACION_DIAS = 30;

const DEFAULT_FECHA_INICIO = '2026-09-19'; // day=19 → prorrateo visible

export function Venta(): JSX.Element {
  const { t } = useTranslation(['suscripciones', 'common']);
  const navigate = useNavigate();
  const [state, setState] = useState<VentaStepState>({ paso: 1 });
  const [placaError, setPlacaError] = useState<string | null>(null);
  const [clienteError, setClienteError] = useState<string | null>(null);
  const [clienteNitInput, setClienteNitInput] = useState('');
  const [clienteNombreInput, setClienteNombreInput] = useState('');
  const [placaInput, setPlacaInput] = useState('');
  const [planInput, setPlanInput] = useState('');
  const { trigger, isMutating } = useVentaSuscripcion();

  const montoProporcional = useMemo<number | null>(() => {
    if (state.paso !== 4 || !state.fecha_inicio_cobertura) return null;
    return calcularMontoProporcional(
      { valor: PLAN_PREVIEW_VALOR, duracion_dias: PLAN_PREVIEW_DURACION_DIAS },
      new Date(state.fecha_inicio_cobertura),
    );
  }, [state.paso, state.fecha_inicio_cobertura]);

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
          <Input
            data-testid="venta-plan-select"
            placeholder="UUID plan"
            value={planInput}
            onChange={(e) => setPlanInput(e.target.value)}
          />
          <Button
            type="button"
            data-testid="venta-paso-3-siguiente"
            onClick={handlePaso3Siguiente}
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
          <PagoModal
            uuid_ingreso={null}
            total_cop={montoProporcional ?? PLAN_PREVIEW_VALOR}
            onSubmit={handlePagoSubmit}
          />
          {isMutating && <span data-testid="venta-mutating">Procesando…</span>}
        </section>
      )}
    </div>
  );
}
