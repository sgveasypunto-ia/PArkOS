/**
 * `<ClienteDatosTab />` — tab "Datos" de `ClienteDetalle` (HU-F20.1).
 * Displays + edits cliente fields via react-hook-form + Zod, submits
 * `PUT /api/v1/clientes/clientes/{uuid}` through the `onSubmit` prop
 * (owned by the page via `useCliente(uuid).update`).
 */
import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import { isConsumidorFinal, type Cliente, type ClienteUpdateInput } from '../api/clientesApi';

// Closed set for the UI only -- `schemas/clientes.py::ClientesRead/Update`
// types `tipo_identificador` as a plain unenforced `str | None`
// server-side. This repo has no shadcn `<Select>` component installed
// (checked `apps/web_admin/src/components/ui/`); every other form in
// this codebase that needs a closed-option dropdown (`UsuariosList.tsx`,
// `UsuarioCrear.tsx`'s `RolStep`, `ClienteIdentificacionFields.tsx` in
// `apps/electron-sucursal`) uses a plain `<select>` styled with the same
// Tailwind classes shadcn's own `Input` uses -- followed here for
// consistency rather than introducing a one-off dependency.
const TIPOS_IDENTIFICADOR = ['CC', 'NIT', 'CE', 'pasaporte'] as const;

const clienteDatosSchema = z.object({
  tipo_identificador: z.enum(TIPOS_IDENTIFICADOR),
  numero_identificacion: z.string().min(1),
  nombre: z.string().optional(),
  apellido: z.string().optional(),
  telefono: z.string().optional(),
  // Standard email validator check (per task brief): no existing
  // shared/reusable email Zod schema was found anywhere in
  // `apps/web_admin/src` (grepped for `z.string().email()` -- the only
  // hits are `features/usuarios/api/usuariosSchema.ts` and
  // `features/auth/api/loginSchema.ts`, each declaring their OWN
  // `z.string().email()` inline, same as here -- there is no shared
  // `lib/validation`-style export to import instead). `.email()` IS the
  // standard mechanism this stack already provides via the mandated Zod
  // dependency, so it's used directly rather than hand-rolling an RFC
  // 5322 regex. `.or(z.literal(''))` allows clearing the field (backend
  // `email` is nullable).
  email: z.string().email().or(z.literal('')).optional(),
});

type ClienteDatosFormValues = z.infer<typeof clienteDatosSchema>;

export interface ClienteDatosTabProps {
  cliente: Cliente;
  onSubmit: (values: ClienteUpdateInput) => Promise<Cliente>;
}

export function ClienteDatosTab({ cliente, onSubmit }: ClienteDatosTabProps): JSX.Element {
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // The billing placeholder client ("Consumidor final") is system-owned.
  const readOnly = isConsumidorFinal(cliente);

  const form = useForm<ClienteDatosFormValues>({
    resolver: zodResolver(clienteDatosSchema),
    defaultValues: {
      tipo_identificador: TIPOS_IDENTIFICADOR.includes(
        cliente.tipo_identificador as (typeof TIPOS_IDENTIFICADOR)[number],
      )
        ? (cliente.tipo_identificador as (typeof TIPOS_IDENTIFICADOR)[number])
        : 'CC',
      numero_identificacion: cliente.numero_identificacion ?? '',
      nombre: cliente.nombre ?? '',
      apellido: cliente.apellido ?? '',
      telefono: cliente.telefono ?? '',
      email: cliente.email ?? '',
    },
  });

  async function handleSubmit(values: ClienteDatosFormValues): Promise<void> {
    if (readOnly) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await onSubmit({
        tipo_identificador: values.tipo_identificador,
        numero_identificacion: values.numero_identificacion,
        nombre: values.nombre ? values.nombre : null,
        apellido: values.apellido ? values.apellido : null,
        telefono: values.telefono ? values.telefono : null,
        email: values.email ? values.email : null,
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : '';
      // NOTA: el backend hoy no emite un 422 estructurado "numero_identificacion_duplicado"
      // para la UK clientes_uk01 (tipo_identificador+numero_identificacion+vigente_desde) —
      // una colisión real probablemente llega como 500 sin manejar. Este bloque anticipa
      // el contrato de plan.md; si el backend nunca lo implementa, el usuario verá el
      // fallback genérico.
      if (/duplicad/i.test(message) || /numero_identificacion_duplicado/i.test(message)) {
        setSubmitError(
          t(
            'clienteDatos.errorDuplicado',
            'Ya existe un cliente con ese número de identificación.',
          ),
        );
      } else {
        setSubmitError(t('clienteDatos.error', 'No se pudo guardar. Reintentá.'));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(handleSubmit)}
        className="space-y-4"
        noValidate
        data-testid="cliente-datos-form"
      >
        <fieldset disabled={readOnly} className="m-0 min-w-0 space-y-4 border-0 p-0">
          {submitError !== null && (
            <p
              role="alert"
              aria-live="assertive"
              data-testid="cliente-datos-submit-error"
              className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {submitError}
            </p>
          )}

          <FormField
            control={form.control}
            name="tipo_identificador"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-tipo-identificador">
                  {t('clienteDatos.tipoIdentificador', 'Tipo de identificación')}
                </FormLabel>
                <FormControl>
                  <select
                    id="cliente-tipo-identificador"
                    data-testid="cliente-field-tipo-identificador"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    {...field}
                  >
                    {TIPOS_IDENTIFICADOR.map((tipo) => (
                      <option key={tipo} value={tipo}>
                        {tipo}
                      </option>
                    ))}
                  </select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="numero_identificacion"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-numero">
                  {t('clienteDatos.numero', 'Número de identificación')}
                </FormLabel>
                <FormControl>
                  <Input id="cliente-numero" data-testid="cliente-field-numero" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="nombre"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-nombre">{t('clienteDatos.nombre', 'Nombre')}</FormLabel>
                <FormControl>
                  <Input id="cliente-nombre" data-testid="cliente-field-nombre" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="apellido"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-apellido">
                  {t('clienteDatos.apellido', 'Apellido')}
                </FormLabel>
                <FormControl>
                  <Input id="cliente-apellido" data-testid="cliente-field-apellido" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="telefono"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-telefono">
                  {t('clienteDatos.telefono', 'Teléfono')}
                </FormLabel>
                <FormControl>
                  <Input id="cliente-telefono" data-testid="cliente-field-telefono" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel htmlFor="cliente-email">{t('clienteDatos.email', 'Email')}</FormLabel>
                <FormControl>
                  <Input
                    id="cliente-email"
                    type="email"
                    data-testid="cliente-field-email"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {readOnly ? (
            <p
              role="note"
              data-testid="cliente-datos-readonly"
              className="rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground"
            >
              {t(
                'clienteDatos.soloLectura',
                'Cliente estándar de facturación (Consumidor final): no se puede editar ni inactivar.',
              )}
            </p>
          ) : (
            <div className="flex justify-end">
              <Button type="submit" disabled={isSubmitting} data-testid="cliente-datos-submit">
                {isSubmitting ? t('common.saving', 'Guardando…') : t('common.save', 'Guardar')}
              </Button>
            </div>
          )}
        </fieldset>
      </form>
    </Form>
  );
}
