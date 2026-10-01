/**
 * `EmpresaMensajesTab` — tab "Mensajes" del singleton Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 * Form con dos textareas:
 *   - `mensaje_bienvenida`: se imprime en el ticket al INGRESO del
 *     vehículo. Hasta 2000 chars.
 *   - `mensaje_salida`: se imprime en el ticket al egreso. Hasta
 *     2000 chars.
 *
 * Incluye un preview tipo "ticket" que muestra cómo se vería el
 * mensaje con el cuerpo actual — útil para revisar saltos de línea
 * y el ancho típico de impresión (32 chars).
 *
 * Container/presentational split (mirror de `EmpresaDatosTab`).
 */
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import {
  empresaMensajesUpdateSchema,
  type EmpresaMensajesUpdateInput,
} from '../api/empresaSchema';
import { updateEmpresaMensajes } from '../api/empresaApi';
import { useEmpresa } from '../hooks/useEmpresa';

const TICKET_WIDTH_CHARS = 32;

function previewTicket(text: string | null | undefined): string {
  if (text === null || text === undefined || text.length === 0) {
    return '(vacío)';
  }
  return text;
}

function EmpresaMensajesForm({
  form,
  onSubmit,
  isSubmitting,
}: {
  form: ReturnType<typeof useForm<EmpresaMensajesUpdateInput>>;
  onSubmit: (values: EmpresaMensajesUpdateInput) => void;
  isSubmitting: boolean;
}): JSX.Element {
  const { t } = useTranslation();
  const bienvenida = form.watch('mensaje_bienvenida');
  const salida = form.watch('mensaje_salida');

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4"
        noValidate
        aria-busy={isSubmitting}
        data-testid="empresa-mensajes-form"
      >
        <FormField
          control={form.control}
          name="mensaje_bienvenida"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="mensaje_bienvenida">
                {t('empresa.mensajes.bienvenida', 'Mensaje de bienvenida')}
              </FormLabel>
              <FormControl>
                <textarea
                  id="mensaje_bienvenida"
                  data-testid="empresa-mensajes-bienvenida"
                  rows={3}
                  maxLength={2000}
                  placeholder="Bienvenido a Parkos. Conserve su ticket."
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="mensaje_salida"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="mensaje_salida">
                {t('empresa.mensajes.salida', 'Mensaje de salida')}
              </FormLabel>
              <FormControl>
                <textarea
                  id="mensaje_salida"
                  data-testid="empresa-mensajes-salida"
                  rows={3}
                  maxLength={2000}
                  placeholder="Gracias por su visita. ¡Hasta pronto!"
                  className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  {...field}
                  value={field.value ?? ''}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
          data-testid="empresa-mensajes-preview"
        >
          <PreviewBlock
            title={t('empresa.mensajes.previewBienvenida', 'Preview ticket de entrada')}
            text={previewTicket(bienvenida)}
            testId="empresa-mensajes-preview-bienvenida"
          />
          <PreviewBlock
            title={t('empresa.mensajes.previewSalida', 'Preview ticket de salida')}
            text={previewTicket(salida)}
            testId="empresa-mensajes-preview-salida"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button
            type="submit"
            disabled={isSubmitting}
            data-testid="empresa-mensajes-submit"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                {t('empresa.mensajes.submitting', 'Guardando…')}
              </>
            ) : (
              t('empresa.mensajes.submit', 'Guardar mensajes')
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function PreviewBlock({
  title,
  text,
  testId,
}: {
  title: string;
  text: string;
  testId: string;
}): JSX.Element {
  return (
    <section
      className="rounded-md border bg-muted/20 p-3"
      data-testid={testId}
    >
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <pre
        className="whitespace-pre-wrap font-mono text-xs"
        style={{ maxWidth: `${TICKET_WIDTH_CHARS}ch` }}
      >
        {text}
      </pre>
    </section>
  );
}

export function EmpresaMensajesTab(): JSX.Element {
  const { t } = useTranslation();
  const { empresa, isLoading, error, refresh } = useEmpresa();

  const form = useForm<EmpresaMensajesUpdateInput>({
    resolver: zodResolver(empresaMensajesUpdateSchema),
    defaultValues: {
      mensaje_bienvenida: empresa?.mensaje_bienvenida ?? '',
      mensaje_salida: empresa?.mensaje_salida ?? '',
    },
  });

  // Mantener defaultValue sincronizado con el singleton en el primer
  // mount, pero no en cada cambio del form (sería un loop).
  useEffect(() => {
    if (empresa === null) return;
    form.reset({
      mensaje_bienvenida: empresa.mensaje_bienvenida ?? '',
      mensaje_salida: empresa.mensaje_salida ?? '',
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresa?.uuid]);

  async function onSubmit(values: EmpresaMensajesUpdateInput): Promise<void> {
    if (empresa === null) return;
    await updateEmpresaMensajes(empresa.uuid, values);
    await refresh();
  }

  if (isLoading) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="empresa-mensajes-loading"
        className="text-sm text-muted-foreground"
      >
        {t('common.loading', 'Cargando…')}
      </p>
    );
  }

  if (error !== undefined) {
    return (
      <p
        role="alert"
        aria-live="assertive"
        data-testid="empresa-mensajes-error"
        className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {error.message}
      </p>
    );
  }

  if (empresa === null) {
    return (
      <p
        role="status"
        aria-live="polite"
        data-testid="empresa-mensajes-empty"
        className="rounded-md border border-dashed bg-muted/40 px-3 py-4 text-sm text-muted-foreground"
      >
        {t(
          'empresa.mensajes.empty',
          'Aún no se sembró el singleton Empresa. Los mensajes no se pueden editar hasta entonces.',
        )}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <p
        className="rounded-md bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
        data-testid="empresa-mensajes-editing"
      >
        {t(
          'empresa.mensajes.editingNotice',
          'Cambiar los mensajes publica una nueva versión bi-temporal. La reimpresión de tickets usa la versión vigente al momento del cierre del ingreso.',
        )}
      </p>
      <EmpresaMensajesForm
        form={form}
        onSubmit={(values) => {
          void onSubmit(values);
        }}
        isSubmitting={form.formState.isSubmitting}
      />
    </div>
  );
}
