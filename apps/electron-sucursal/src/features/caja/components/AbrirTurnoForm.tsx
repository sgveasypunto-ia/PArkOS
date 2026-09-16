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
import type { UseFormReturn } from 'react-hook-form';
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

import type { AbrirTurnoInput } from '../api/schemas/turnoSchema';

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
  form: UseFormReturn<AbrirTurnoInput>;
  onSubmit: (data: AbrirTurnoInput) => Promise<void>;
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
          <CardContent>

        <FormField
          control={form.control}
          name="valor_inicial_efectivo"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorInicialEfectivo')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="abrir-turno-valor-efectivo"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="valor_inicial_datafono"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('caja:valorInicialDatafono')}</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  step="0.01"
                  min="0"
                  data-testid="abrir-turno-valor-datafono"
                  value={field.value ?? ''}
                  onChange={(e) => {
                    const raw = e.target.value;
                    field.onChange(raw === '' ? 0 : Number(raw));
                  }}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
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
          className="w-full mt-4"
        >
          {isSubmitting ? t('common:loading') : t('caja:abrirTurno')}
        </Button>
          </CardContent>
        </Card>
      </form>
    </Form>
  );
}