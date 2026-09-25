/**
 * `<AbrirTurnoForm />` — presentational puro (F3.3 — T2, DEC-F3.3-01 verbatim).
 *
 * Recibe props `{ form, onSubmit, isSubmitting, error }` (DEC-F3.1-02 verbatim).
 * NO accede a `useAuth` ni `sesionActivaApi.abrirSesion` directamente — la
 * integración backend vive en `<AbrirTurno>` container.
 *
 * Accesibilidad (RNF-022 WCAG 2.1 AA — REQ-OPS-119 S3 + REQ-OPS-124 S3):
 *   - `<Form {...form}>` envuelve con FormProvider (form.tsx:33).
 *   - `<FormLabel htmlFor>` + `<FormControl id>` asociados via `useFormField()`.
 *   - `<Input type="number" inputMode="decimal" step="0.01">` — teclado
 *     numérico mobile/electron (DEC-F3.3-02).
 *   - `<FormMessage role="alert">` para errores Zod (live region).
 * - 409 SesionAlreadyActiveError → `<FormMessage role="alert">{t('sesionYaAbierta')}</FormMessage>`
 *     + `<Button onClick={() => navigate('/')}>{t('irAlTurno')}</Button>` (DEC-F3.3-08).
 *
 * NOTA: el botón "Ir al turno" usa `<Button type="button" onClick={onIrAlTurno}>`
 * para que NO triggeree submit del form (type="submit" por default en F2.1 button.tsx).
 */
import type { FormEventHandler } from 'react';
import type { Control, UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import {
  NUMERIC_INPUT_REGEX,
  type AbrirTurnoInput,
} from '../api/schemas/turnoSchema';

/**
 * Raw RHF form-state shape — BEFORE `abrirTurnoSchema`'s `.transform()`
 * coerces the numeric fields to `number` on submit. The operator types
 * into a `type="text"` input (see `NUMERIC_INPUT_REGEX` below) so the
 * live form state MUST stay `string`; `AbrirTurnoInput` (turnoSchema.ts)
 * is the POST-transform/output shape the submit handler receives.
 */
export type AbrirTurnoFormValues = Omit<
  AbrirTurnoInput,
  'valor_inicial_efectivo' | 'valor_inicial_datafono'
> & {
  valor_inicial_efectivo: string;
  valor_inicial_datafono: string;
};

/**
 * Estado de error que `<AbrirTurno>` pasa a `<AbrirTurnoForm />` para render.
 *  - sesion_already_active → <FormMessage role="alert">{t('sesionYaAbierta')}</FormMessage>
 *                            + Button "Ir al turno".
 *  - network               → <FormMessage role="alert">{t('errors:serverError')}</FormMessage>
 */
export type AbrirTurnoErrorState =
  | { kind: 'sesion_already_active' }
  | { kind: 'network' }
  | null;

export interface AbrirTurnoFormProps {
  form: UseFormReturn<AbrirTurnoFormValues, unknown, AbrirTurnoInput>;
  // The container already wraps its data handler with
  // `form.handleSubmit(...)` (see `<AbrirTurno>`), so this prop is the
  // native form event handler, not the raw `AbrirTurnoInput` data
  // handler — it is bound directly to `<form onSubmit={onSubmit}>`
  // below.
  onSubmit: FormEventHandler<HTMLFormElement>;
  isSubmitting: boolean;
  error: AbrirTurnoErrorState;
  onIrAlTurno: () => void;
}

export function AbrirTurnoForm({
  form,
  onSubmit,
  isSubmitting,
  error,
  onIrAlTurno,
}: AbrirTurnoFormProps): JSX.Element {
  const { t } = useTranslation(['caja', 'common']);

  // shadcn's <FormField>/<Controller> only read/write the pre-transform
  // (Input) field shape — the Output type param (post zodResolver
  // `.transform()`) is irrelevant to field wiring, but its 3-generic
  // `Control<Input, Context, Output>` doesn't structurally match the
  // 1-generic `Control<TFieldValues>` that <FormField> expects. Narrowing
  // here (once) documents that this is a known, safe RHF+Zod-transform
  // limitation, not a silenced type error.
  const control = form.control as unknown as Control<AbrirTurnoFormValues>;

  return (
    <Form {...form}>
      <form
        onSubmit={onSubmit}
        noValidate
        aria-labelledby="abrir-turno-title"
        data-testid="abrir-turno-form"
        className="space-y-4"
      >
        <Card>
          <CardHeader>
            <CardTitle id="abrir-turno-title" asChild>
              <h1>{t('caja:abrirTurno')}</h1>
            </CardTitle>
          </CardHeader>
          {/* F31.3 rediseño: `space-y-4` agregado — los 3 FormField +
              banner de error + botón submit eran hijos directos de
              CardContent sin ningún spacing entre sí (el `space-y-4`
              de más arriba está en el `<form>`, cuyo único hijo es
              `<Card>`, así que no llegaba a espaciar nada adentro). */}
          <CardContent className="space-y-4">

        <FormField
          control={control}
          name="valor_inicial_efectivo"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorInicialEfectivo')}</FormLabel>
              <FormControl>
                {/* type="text" + regex filter (NUMERIC_INPUT_REGEX del
                   schema) -- los inputs numéricos `type="number"`
                   tienen quirks en Electron/Chromium que el operador
                   sufria: defaultValue=0 que no se podia borrar,
                   scroll-wheels que cambiaban el valor, etc. Con
                   text + filtro el operador puede borrar, tipear
                   libremente, pegar, y los keystrokes invalidos se
                   caen silenciosamente sin tocar el field. Schema
                   valida la misma regex en blur/submit; ver
                   api/schemas/turnoSchema.ts. */}
                <Input
                  {...field}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  data-testid="abrir-turno-valor-efectivo"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '' || NUMERIC_INPUT_REGEX.test(raw)) {
                      // Mantenemos el field como string en form state
                      // (coherente con el schema). El transform del
                      // schema lo convierte a number en submit.
                      field.onChange(raw);
                    }
                  }}
                  placeholder={t('caja:valorInicialEfectivoPlaceholder', {
                    defaultValue: 'Ingrese aquí el valor…',
                  })}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="valor_inicial_datafono"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorInicialDatafono')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  data-testid="abrir-turno-valor-datafono"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === '' || NUMERIC_INPUT_REGEX.test(raw)) {
                      field.onChange(raw);
                    }
                  }}
                  placeholder={t('caja:valorInicialDatafonoPlaceholder', {
                    defaultValue: 'Ingrese aquí el valor…',
                  })}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="observaciones"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:observaciones')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="text"
                  data-testid="abrir-turno-observaciones"
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormDescription>Opcional</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {error?.kind === 'sesion_already_active' && (
          <>
            <FormMessage role="alert" data-testid="abrir-turno-error-sesion-ya-abierta">
              {t('caja:sesionYaAbierta')}
            </FormMessage>
            <Button
              type="button"
              onClick={onIrAlTurno}
              data-testid="abrir-turno-ir-al-turno"
            >
              {t('caja:irAlTurno')}
            </Button>
          </>
        )}

        {error?.kind === 'network' && (
          <p role="alert" data-testid="abrir-turno-error-network">
            {t('common:error')}
          </p>
        )}

        <Button
          type="submit"
          disabled={isSubmitting}
          aria-disabled={isSubmitting}
          data-testid="abrir-turno-submit"
          // `mt-4` removido — redundante ahora que CardContent tiene
          // `space-y-4` (antes compensaba la falta de spacing general).
          className="w-full"
        >
          {isSubmitting ? t('common:loading') : t('caja:abrirTurno')}
        </Button>
          </CardContent>
        </Card>
      </form>
    </Form>
  );
}