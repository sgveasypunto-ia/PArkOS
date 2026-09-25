/**
 * `<PagoModal />` — extracted presentational component for the F8.1
 * payment flow (HU-F8.1, REQ-OPS-167).
 *
 * Owned by:
 *   - medio_pago discriminator (efectivo | datafono)
 *   - monto_recibido (efectivo) | voucher (datafono)
 *   - FE toggle + conditional NIT/DV/nombre/email fields
 *   - vueltos computed via useMemo (inline — ABIERTO-200 follow-up
 *     creates `useVueltos` after F8.1 lands; per F7.1 `useCountdown`
 *     precedent, the inline implementation is acceptable while
 *     ABIERTO-200 stays open)
 *   - `validarNitModulo11` (BR7 / DEC-SUC-29) for FE NIT validation
 *
 * The component is purely presentational — `<PagoSheet>` mounts it
 * inside the right-side drawer and wires the print-trigger side
 * effects (DEC-SUC-27: CU-15S print fires AFTER pago, then recibo
 * de pago).
 */
import { useEffect, useId, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { validarNitModulo11 } from '../../../lib/validation/nit';
import { validarIdentificacion, type TipoIdentificador } from '../../../lib/validation/identificacion';
import { formatCOP } from '../../../features/caja/lib/format';

/**
 * Placeholder de ejemplo por tipo de documento — puramente cosmético.
 * BUGFIX (2026-09-25, directiva del operador): antes el input `nit` se
 * precargaba con el sentinel real de consumidor final
 * (`222222222222222`) como VALOR de estado, no como placeholder — acá
 * solo se muestra un ejemplo de formato; el sentinel de consumidor
 * final vive exclusivamente en `PagoSheet`/`Venta`, que lo usan para
 * armar el payload cuando `fe===false` (cliente genérico).
 */
const NUMERO_PLACEHOLDER: Record<TipoIdentificador, string> = {
  NIT: '900123456-7',
  CC: '1020304050',
  CE: '1020304050',
  pasaporte: 'AB1234567',
};

/**
 * Discriminated union: the payment payload shape differs between
 * efectivo (monto_recibido_cop drives vueltos) and datafono (voucher
 * is required, no vueltos). Zod's discriminated union enforces the
 * discriminator at the schema boundary.
 */
const tipoPersonaSchema = z.enum(['persona', 'empresa']);
const tipoIdentificadorSchema = z.enum(['NIT', 'CC', 'CE', 'pasaporte']);

const pagoEfectivoSchema = z.object({
  medio_pago: z.literal('efectivo'),
  monto_recibido_cop: z.coerce.number().int().positive(),
  voucher: z.string().optional(),
  fe: z.boolean(),
  tipo_persona: tipoPersonaSchema,
  tipo_identificador: tipoIdentificadorSchema,
  nit: z.string().trim().optional(),
  dv: z.string().trim().optional(),
  nombre_cliente: z.string().trim().optional(),
  apellido: z.string().trim().optional(),
  email_cliente: z
    .string()
    .trim()
    .email('email_formato_invalido')
    .optional()
    .or(z.literal('')),
});

const pagoDatafonoSchema = z.object({
  medio_pago: z.literal('datafono'),
  voucher: z.string().trim().min(1, 'voucher_requerido'),
  fe: z.boolean(),
  tipo_persona: tipoPersonaSchema,
  tipo_identificador: tipoIdentificadorSchema,
  nit: z.string().trim().optional(),
  dv: z.string().trim().optional(),
  nombre_cliente: z.string().trim().optional(),
  apellido: z.string().trim().optional(),
  email_cliente: z
    .string()
    .trim()
    .email('email_formato_invalido')
    .optional()
    .or(z.literal('')),
});

/**
 * Cross-field validation for the FE ("factura a nombre del cliente")
 * block. Only runs when `fe===true` — unchecked stays "cliente
 * genérico" (PagoSheet omits `fe_datos_cliente` entirely) and none of
 * these fields matter. When checked, the operator MUST supply a real
 * document (validated per `tipo_identificador` via
 * `validarIdentificacion`) and a nombre; `apellido` is only required
 * for persona natural (empresa uses `nombre` as razón social, no
 * apellido — mirrors `.mmd` `clientes.apellido`: "vacío para persona
 * jurídica").
 */
function validarBloqueFe(
  values: {
    fe: boolean;
    tipo_persona: 'persona' | 'empresa';
    tipo_identificador: TipoIdentificador;
    nit?: string;
    dv?: string;
    nombre_cliente?: string;
    apellido?: string;
  },
  ctx: z.RefinementCtx,
): void {
  if (!values.fe) return;

  const numero = values.nit?.trim() ?? '';
  if (numero.length < 5) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['nit'],
      message: 'numero_identificacion_requerido',
    });
  } else if (values.tipo_identificador !== 'NIT') {
    const resultado = validarIdentificacion(values.tipo_identificador, numero);
    if (!resultado.ok) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['nit'],
        message: resultado.motivo ?? 'documento_formato_invalido',
      });
    }
  }

  if (!values.nombre_cliente?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['nombre_cliente'],
      message: 'nombre_requerido',
    });
  }

  if (values.tipo_persona === 'persona' && !values.apellido?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['apellido'],
      message: 'apellido_requerido',
    });
  }

  if (values.tipo_identificador === 'NIT') {
    const dv = values.dv?.trim() ?? '';
    if (dv.length !== 1 || !/^[0-9]$/.test(dv)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dv'],
        message: 'dv_requerido',
      });
    } else if (numero.length >= 5 && !validarNitModulo11(numero, dv).ok) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['dv'],
        message: 'dv_invalido',
      });
    }
  }
}

// Schema defined locally; only the type is exported for consumers
// (PagoModal.test.tsx, PagoSheet.test.tsx). Constraining exports
// to the type-only satisfies react-refresh/only-export-components.
const pagoFormSchema = z
  .discriminatedUnion('medio_pago', [pagoEfectivoSchema, pagoDatafonoSchema])
  .superRefine(validarBloqueFe);
export type PagoFormValues = z.infer<typeof pagoFormSchema>;

export interface PagoModalProps {
  /**
   * UUID del ingreso activo que se está pagando, o `null` cuando el
   * cobro no está atado a un ingreso (venta de suscripción, F11.3
   * `<Venta />` wizard). El componente NO lo usa para nada — el
   * caller ya decide cuándo montar `<PagoModal>` y arma el POST con
   * lo que corresponda; queda en la prop solo como metadata para el
   * caller/tests.
   *
   * BUGFIX (2026-09-25, encontrado por el operador con una captura de
   * pantalla real): el submit y el botón "Confirmar pago" estaban
   * gateados con `!uuid_ingreso`, un remanente del único consumidor
   * original (`<PagoSheet />`, salida de vehículo). Cuando `<Venta />`
   * empezó a reusar este componente pasando `uuid_ingreso={null}` a
   * propósito, el botón quedaba permanentemente deshabilitado y
   * ninguna venta de suscripción podía cobrarse.
   */
  uuid_ingreso: string | null;
  /**
   * Total a cobrar (centavos / unidades COP según el call site —
   * el modal opera con unidades enteras que pasan tal cual al
   * hook `useRegistrarPago`).
   */
  total_cop: number;
  /**
   * Submit handler — receives the parsed `PagoFormValues` (after Zod
   * validation). `<PagoSheet>` wires this to `useRegistrarPago`
   * + the post-pago print trigger pipeline.
   */
  onSubmit: (values: PagoFormValues) => Promise<void>;
  /**
   * F11.3 follow-up (Suscribirse Venta wizard) -- optional pre-fill
   * for the FE cliente fields. When supplied, the wizard already
   * collected nit/nombre/email at step 1 and we want them pre-populated
   * in the PagoModal instead of the consumidor final fallback.
   * Pass `fe: true` to flip the "Generar FE" toggle ON at step 4 entry
   * (operator can untick if they want a no-FE sale). Defaults preserved
   * for the existing `<PagoSheet />` caller -- it passes nothing and
   * gets the consumidor final NIT / nombre.
   */
  clientePrefill?: {
    nit?: string;
    nombre?: string;
    email?: string;
    fe?: boolean;
    /** Persona natural vs. empresa — default `'empresa'` (preserva el
     * comportamiento histórico NIT-only cuando el caller no lo pasa). */
    tipo_persona?: 'persona' | 'empresa';
    tipo_identificador?: TipoIdentificador;
    apellido?: string;
  };
}

/**
 * `<PagoModal />` — presentational form for the F8.1 payment flow.
 * No `Sheet` mounting, no drawer-store coupling — the host decides
 * WHEN to display it (REQ-OPS-139 lazy-mount). RHF + Zod resolver;
 * vueltos via `useMemo` (inline; ABIERTO-200 extracts `useVueltos`).
 */
export function PagoModal({
  total_cop,
  onSubmit,
  clientePrefill,
}: PagoModalProps): JSX.Element {
  const { t } = useTranslation(['facturacion', 'common']);
  const formId = useId();

  // Snapshot the prefill ONCE on mount so the wizard's step-1 cliente
  // data drives the initial PagoModal values. Subsequent re-renders
  // (e.g. `total_cop` change) preserve the user's typed corrections
  // by re-using `form.reset(...)` below with the same prefill snapshot.
  const initialPrefill = clientePrefill;

  // BUGFIX (2026-09-25, directiva del operador): "si se selecciona [el
  // checkbox FE] se debe tener placeholders no valores sobre el input".
  // `nit`/`nombre_cliente` arrancan VACÍOS (o con lo que el wizard de
  // suscripción haya recolectado en su paso 1) — nunca con el sentinel
  // de consumidor final. Ese sentinel (`NIT_CONSUMIDOR_FINAL`) sigue
  // viviendo SOLO en `PagoSheet`/`Venta`, para armar el payload cuando
  // `fe===false` (cliente genérico); ya no contamina el estado del form.
  const form = useForm<PagoFormValues>({
    resolver: zodResolver(pagoFormSchema),
    defaultValues: {
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      voucher: '',
      fe: initialPrefill?.fe ?? false,
      tipo_persona: initialPrefill?.tipo_persona ?? 'empresa',
      tipo_identificador: initialPrefill?.tipo_identificador ?? 'NIT',
      nit: initialPrefill?.nit ?? '',
      dv: '',
      nombre_cliente: initialPrefill?.nombre ?? '',
      apellido: initialPrefill?.apellido ?? '',
      email_cliente: initialPrefill?.email ?? '',
    },
    mode: 'onSubmit',
  });

  // Reset defaults when total changes (e.g. operator re-cotiza).
  // Preserves the prefill values when provided (existing page
  // route passes nothing and keeps the empty/genérico fallback).
  useEffect(() => {
    form.reset({
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      voucher: '',
      fe: initialPrefill?.fe ?? false,
      tipo_persona: initialPrefill?.tipo_persona ?? 'empresa',
      tipo_identificador: initialPrefill?.tipo_identificador ?? 'NIT',
      nit: initialPrefill?.nit ?? '',
      dv: '',
      nombre_cliente: initialPrefill?.nombre ?? '',
      apellido: initialPrefill?.apellido ?? '',
      email_cliente: initialPrefill?.email ?? '',
    });
  }, [total_cop, form, initialPrefill]);

  const medioPago = useWatch({ control: form.control, name: 'medio_pago' });
  const feActive = useWatch({ control: form.control, name: 'fe' });
  const tipoPersona = useWatch({ control: form.control, name: 'tipo_persona' });
  const tipoIdentificador = useWatch({ control: form.control, name: 'tipo_identificador' });
  const nitValue = useWatch({ control: form.control, name: 'nit' }) ?? '';
  const dvValue = useWatch({ control: form.control, name: 'dv' }) ?? '';
  const montoValue = useWatch({ control: form.control, name: 'monto_recibido_cop' });

  // vueltos computed inline — when medio_pago is `efectivo` AND the
  // operator has typed a monto_recibido greater than the total, the
  // vueltos display shows the positive difference; otherwise "—".
  const vueltos = useMemo<string>(() => {
    if (medioPago !== 'efectivo') return '—';
    const numericMonto = typeof montoValue === 'number'
      ? montoValue
      : Number(montoValue);
    if (!Number.isFinite(numericMonto) || numericMonto <= total_cop) return '—';
    return formatCOP(numericMonto - total_cop);
  }, [medioPago, montoValue, total_cop]);

  // Inline DV error from validarNitModulo11 (BR7) — surfaced while the
  // operator types so they get the corrective hint immediately. DV is
  // an exclusively-NIT concept (CC/CE/pasaporte have no dígito de
  // verificación in Colombia), so this only applies when the chosen
  // tipo_identificador is NIT.
  const dvError = useMemo<string | null>(() => {
    if (!feActive || tipoIdentificador !== 'NIT') return null;
    const stripped = nitValue.replace(/\D+/g, '');
    if (stripped.length < 6) return null;
    if (dvValue.length !== 1 || !/^[0-9]$/.test(dvValue)) {
      return 'dv debe ser 0-9';
    }
    const result = validarNitModulo11(stripped, dvValue);
    if (result.ok) return null;
    return `DV inválido (esperado ${result.dvEsperado})`;
  }, [feActive, tipoIdentificador, nitValue, dvValue]);

  // HU-F8.1 — bloquea el submit en cliente si el efectivo recibido es
  // menor al total (código de error `monto_insuficiente`). El backend
  // también rechazaría con 4xx, pero el bloqueo cliente evita el
  // round-trip y muestra el FormMessage inline antes de tocar la red.
  const handleSubmit = form.handleSubmit(async (values) => {
    if (
      values.medio_pago === 'efectivo' &&
      values.monto_recibido_cop < total_cop
    ) {
      form.setError('monto_recibido_cop', {
        type: 'manual',
        message: t('facturacion:pago.monto_insuficiente', {
          defaultValue: `Monto recibido es menor al total (${formatCOP(total_cop)})`,
        }),
      });
      return;
    }
    await onSubmit(values);
  });

  return (
    <Form {...form}>
      <form
        id={formId}
        onSubmit={handleSubmit}
        className="space-y-4 py-4"
        data-testid="pago-modal"
      >
        <FormField
          control={form.control}
          name="medio_pago"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('facturacion:pago.medioPago', { defaultValue: 'Medio de pago' })}</FormLabel>
              <FormControl>
                {/* F31.3 — select nativo (shadcn no trae <Select> HTML
                    nativo en este baseline); se alinea a las mismas
                    clases/estados que <Input> (focus-visible, disabled,
                    hover) en vez del `shadow-sm` suelto que tenía antes. */}
                <select
                  data-testid="pago-medio-pago"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors hover:border-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                >
                  <option value="efectivo">{t('facturacion:pago.medio_efectivo', { defaultValue: 'Efectivo' })}</option>
                  <option value="datafono">{t('facturacion:pago.medio_datafono', { defaultValue: 'Datáfono' })}</option>
                </select>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {medioPago === 'efectivo' && (
          <>
            <FormField
              control={form.control}
              name="monto_recibido_cop"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.montoRecibido', { defaultValue: 'Monto recibido' })}</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      inputMode="numeric"
                      data-testid="pago-monto-recibido"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="text-sm flex justify-between" data-testid="pago-vueltos-row">
              <span className="text-muted-foreground">{t('facturacion:pago.vueltos', { defaultValue: 'Vueltos' })}:</span>
              <span data-testid="pago-vueltos" className="font-medium">
                {vueltos}
              </span>
            </div>
          </>
        )}

        {medioPago === 'datafono' && (
          <FormField
            control={form.control}
            name="voucher"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('facturacion:pago.voucher_label', { defaultValue: 'Voucher (datáfono)' })}</FormLabel>
                <FormControl>
                  <Input data-testid="pago-voucher" {...field} />
                </FormControl>
                <FormMessage data-testid="pago-voucher-error" />
              </FormItem>
            )}
          />
        )}

        <FormField
          control={form.control}
          name="fe"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center gap-2 space-y-0">
              <FormControl>
                {/* F31.3 — checkbox nativo sin ninguna clase (tamaño/color
                    de navegador por defecto, sin focus-ring de marca). */}
                <input
                  type="checkbox"
                  data-testid="pago-fe-toggle"
                  checked={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
                  className="h-4 w-4 shrink-0 rounded border border-input accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                />
              </FormControl>
              <FormLabel className="!mt-0">
                {t('facturacion:pago.fe_toggle', {
                  defaultValue:
                    'Factura a nombre del cliente (opcional); por defecto, factura a consumidor final',
                })}
              </FormLabel>
            </FormItem>
          )}
        />

        {feActive && (
          <div className="space-y-2 border-l-2 border-muted pl-4">
            <FormField
              control={form.control}
              name="tipo_persona"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.tipo_persona_label', { defaultValue: 'Tipo de cliente' })}</FormLabel>
                  <FormControl>
                    <select
                      data-testid="pago-tipo-persona"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors hover:border-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                      value={field.value}
                      onChange={(event) => {
                        const next = event.target.value as 'persona' | 'empresa';
                        field.onChange(next);
                        // Empresa siempre factura con NIT; persona natural
                        // elige su documento (por defecto CC al cambiar
                        // desde empresa, para no dejar el select en un
                        // valor huérfano).
                        if (next === 'empresa') {
                          form.setValue('tipo_identificador', 'NIT');
                        } else if (form.getValues('tipo_identificador') === 'NIT') {
                          form.setValue('tipo_identificador', 'CC');
                        }
                      }}
                      onBlur={field.onBlur}
                    >
                      <option value="empresa">{t('facturacion:pago.tipo_persona_empresa', { defaultValue: 'Empresa' })}</option>
                      <option value="persona">{t('facturacion:pago.tipo_persona_natural', { defaultValue: 'Persona natural' })}</option>
                    </select>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {tipoPersona === 'persona' && (
              <FormField
                control={form.control}
                name="tipo_identificador"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('facturacion:pago.tipo_documento_label', { defaultValue: 'Tipo de documento' })}</FormLabel>
                    <FormControl>
                      <select
                        data-testid="pago-tipo-documento"
                        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background transition-colors hover:border-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                        value={field.value}
                        onChange={field.onChange}
                        onBlur={field.onBlur}
                      >
                        <option value="CC">{t('facturacion:pago.tipo_documento_cc', { defaultValue: 'Cédula de ciudadanía' })}</option>
                        <option value="CE">{t('facturacion:pago.tipo_documento_ce', { defaultValue: 'Cédula de extranjería' })}</option>
                        <option value="pasaporte">{t('facturacion:pago.tipo_documento_pasaporte', { defaultValue: 'Pasaporte' })}</option>
                      </select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="nit"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {tipoIdentificador === 'NIT'
                      ? t('facturacion:pago.fe_nit', { defaultValue: 'NIT del cliente' })
                      : t('facturacion:pago.fe_numero_identificacion', { defaultValue: 'Número de identificación' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-nit"
                      placeholder={NUMERO_PLACEHOLDER[tipoIdentificador]}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {tipoIdentificador === 'NIT' && (
              <FormField
                control={form.control}
                name="dv"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('facturacion:pago.fe_dv', { defaultValue: 'DV (módulo 11)' })}</FormLabel>
                    <FormControl>
                      <Input
                        data-testid="pago-fe-dv"
                        inputMode="numeric"
                        maxLength={1}
                        placeholder="0-9"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage data-testid="pago-fe-dv-error">
                      {dvError ?? ''}
                    </FormMessage>
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="nombre_cliente"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {tipoPersona === 'persona'
                      ? t('facturacion:pago.fe_nombres', { defaultValue: 'Nombres' })
                      : t('facturacion:pago.fe_razon_social', { defaultValue: 'Razón social' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-fe-nombre"
                      placeholder={
                        tipoPersona === 'persona'
                          ? t('facturacion:pago.fe_nombres_placeholder', { defaultValue: 'Ej: Juan Pérez' })
                          : t('facturacion:pago.fe_razon_social_placeholder', { defaultValue: 'Ej: Comercializadora S.A.S.' })
                      }
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {tipoPersona === 'persona' && (
              <FormField
                control={form.control}
                name="apellido"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('facturacion:pago.fe_apellidos', { defaultValue: 'Apellidos' })}</FormLabel>
                    <FormControl>
                      <Input
                        data-testid="pago-fe-apellido"
                        placeholder={t('facturacion:pago.fe_apellidos_placeholder', { defaultValue: 'Ej: Gómez' })}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="email_cliente"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.fe_email', { defaultValue: 'Email (opcional)' })}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-fe-email"
                      type="email"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}

        <div className="flex justify-end pt-4">
          <Button
            type="submit"
            disabled={form.formState.isSubmitting}
            data-testid="pago-confirmar"
          >
            {t('facturacion:pago.confirmar', { defaultValue: 'Confirmar pago' })}
          </Button>
        </div>
      </form>
    </Form>
  );
}