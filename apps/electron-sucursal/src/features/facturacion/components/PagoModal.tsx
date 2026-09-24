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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { validarNitModulo11 } from '../../../lib/validation/nit';
import { formatCOP } from '../../../features/caja/lib/format';

/**
 * FE always defaults to consumidor final per plan.md:1828-1922
 * (NIT `222222222222222`).
 */
const NIT_CONSUMIDOR_FINAL = '222222222222222';

/**
 * Discriminated union: the payment payload shape differs between
 * efectivo (monto_recibido_cop drives vueltos) and datafono (voucher
 * is required, no vueltos). Zod's discriminated union enforces the
 * discriminator at the schema boundary.
 */
const pagoEfectivoSchema = z.object({
  medio_pago: z.literal('efectivo'),
  monto_recibido_cop: z.coerce.number().int().positive(),
  voucher: z.string().optional(),
  fe: z.boolean(),
  nit: z.string().trim().optional(),
  dv: z.string().trim().optional(),
  nombre_cliente: z.string().trim().optional(),
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
  nit: z.string().trim().optional(),
  dv: z.string().trim().optional(),
  nombre_cliente: z.string().trim().optional(),
  email_cliente: z
    .string()
    .trim()
    .email('email_formato_invalido')
    .optional()
    .or(z.literal('')),
});

// Schema defined locally; only the type is exported for consumers
// (PagoModal.test.tsx, PagoSheet.test.tsx). Constraining exports
// to the type-only satisfies react-refresh/only-export-components.
const pagoFormSchema = z.discriminatedUnion('medio_pago', [
  pagoEfectivoSchema,
  pagoDatafonoSchema,
]);
export type PagoFormValues = z.infer<typeof pagoFormSchema>;

export interface PagoModalProps {
  /**
   * UUID del ingreso activo que se está pagando. Required to issue
   * the POST against `/api/v1/facturacion/factura`.
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
  };
}

/**
 * `<PagoModal />` — presentational form for the F8.1 payment flow.
 * No `Sheet` mounting, no drawer-store coupling — the host decides
 * WHEN to display it (REQ-OPS-139 lazy-mount). RHF + Zod resolver;
 * vueltos via `useMemo` (inline; ABIERTO-200 extracts `useVueltos`).
 */
export function PagoModal({
  uuid_ingreso,
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

  const form = useForm<PagoFormValues>({
    resolver: zodResolver(pagoFormSchema),
    defaultValues: {
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      voucher: '',
      fe: initialPrefill?.fe ?? false,
      nit: initialPrefill?.nit ?? NIT_CONSUMIDOR_FINAL,
      dv: '',
      nombre_cliente: initialPrefill?.nombre ?? 'Consumidor final',
      email_cliente: initialPrefill?.email ?? '',
    },
    mode: 'onSubmit',
  });

  // Reset defaults when total changes (e.g. operator re-cotiza).
  // Preserves the prefill values when provided (existing page
  // route passes nothing and keeps the consumidor final fallback).
  useEffect(() => {
    form.reset({
      medio_pago: 'efectivo',
      monto_recibido_cop: total_cop,
      voucher: '',
      fe: initialPrefill?.fe ?? false,
      nit: initialPrefill?.nit ?? NIT_CONSUMIDOR_FINAL,
      dv: '',
      nombre_cliente: initialPrefill?.nombre ?? 'Consumidor final',
      email_cliente: initialPrefill?.email ?? '',
    });
  }, [total_cop, form, initialPrefill]);

  const medioPago = useWatch({ control: form.control, name: 'medio_pago' });
  const feActive = useWatch({ control: form.control, name: 'fe' });
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

  // Inline DV error from validarNitModulo11 (BR7) — surfaced while
  // the operator types so they get the corrective hint immediately.
  const dvError = useMemo<string | null>(() => {
    if (!feActive) return null;
    const stripped = nitValue.replace(/\D+/g, '');
    if (stripped.length < 6) return null;
    if (dvValue.length !== 1 || !/^[0-9]$/.test(dvValue)) {
      return 'dv debe ser 0-9';
    }
    const result = validarNitModulo11(stripped, dvValue);
    if (result.ok) return null;
    return `DV inválido (esperado ${result.dvEsperado})`;
  }, [feActive, nitValue, dvValue]);

  // HU-F8.1 — bloquea el submit en cliente si el efectivo recibido es
  // menor al total (código de error `monto_insuficiente`). El backend
  // también rechazaría con 4xx, pero el bloqueo cliente evita el
  // round-trip y muestra el FormMessage inline antes de tocar la red.
  const handleSubmit = form.handleSubmit(async (values) => {
    if (!uuid_ingreso) return;
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
                <select
                  data-testid="pago-medio-pago"
                  className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
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
                <input
                  type="checkbox"
                  data-testid="pago-fe-toggle"
                  checked={field.value}
                  onChange={field.onChange}
                  onBlur={field.onBlur}
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
              name="nit"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.fe_nit', { defaultValue: 'NIT del cliente' })}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-nit"
                      placeholder={NIT_CONSUMIDOR_FINAL}
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    {t('facturacion:pago.fe_consumidor_final', { defaultValue: 'Consumidor final = 222222222222222' })}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
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
            <FormField
              control={form.control}
              name="nombre_cliente"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('facturacion:pago.fe_nombre', { defaultValue: 'Nombre del cliente' })}</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="pago-fe-nombre"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
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
            disabled={!uuid_ingreso || form.formState.isSubmitting}
            data-testid="pago-confirmar"
          >
            {t('facturacion:pago.confirmar', { defaultValue: 'Confirmar pago' })}
          </Button>
        </div>
      </form>
    </Form>
  );
}