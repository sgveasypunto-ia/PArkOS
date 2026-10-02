/**
 * `<TransicionAnulacionModal />` -- HU-F20.3 confirmation modal for
 * advancing an anulación's chain via
 * `POST /workflows/anulaciones/{uuid}/transicion`. Mirrors
 * `alertas/components/DescartarAlertaModal.tsx`'s RHF+Zod form pattern
 * 1:1, parameterized on the destination `estado` (the caller --
 * `AnulacionDetalle` -- only ever opens this with a destination that is
 * legal for the chain's CURRENT tip, per `ANULACION_TRANSICIONES`).
 *
 * `motivo` is mandatory (BE: non-blank + `extra='forbid'`) -- the submit
 * button stays disabled until RHF's zodResolver validates a non-blank
 * value.
 *
 * 409 `IllegalTransitionError` is a distinct, expected outcome -- a
 * concurrent actor already moved the chain -- so it gets its own clear
 * message instead of the generic error banner text, and
 * `onTransicionada` is NOT called.
 */
import { useState } from 'react';
import type { HTMLAttributes } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import {
  IllegalTransitionError,
  PermissionDeniedError,
  TenantScopeViolationError,
  transicionarAnulacion,
} from '../api/anulacionesApi';
import {
  anulacionTransicionFormSchema,
  type AnulacionEstado,
  type AnulacionRead,
  type AnulacionTransicionFormInput,
} from '../api/anulacionesSchema';

export interface TransicionAnulacionModalProps {
  uuidAnulacion: string;
  estadoDestino: Exclude<AnulacionEstado, 'iniciada'>;
  open: boolean;
  onClose: () => void;
  onTransicionada: (updated: AnulacionRead) => void;
}

const ACCION_COPY: Record<
  Exclude<AnulacionEstado, 'iniciada'>,
  { titleKey: string; title: string; descriptionKey: string; description: string; submitKey: string; submit: string }
> = {
  autorizada: {
    titleKey: 'anulaciones.transicion.autorizada.title',
    title: 'Aprobar anulación',
    descriptionKey: 'anulaciones.transicion.autorizada.description',
    description: 'Esta acción aprueba la anulación y la deja lista para ejecutarse.',
    submitKey: 'anulaciones.transicion.autorizada.submit',
    submit: 'Aprobar',
  },
  ejecutada: {
    titleKey: 'anulaciones.transicion.ejecutada.title',
    title: 'Ejecutar anulación',
    descriptionKey: 'anulaciones.transicion.ejecutada.description',
    description: 'Esta acción ejecuta la anulación de forma definitiva.',
    submitKey: 'anulaciones.transicion.ejecutada.submit',
    submit: 'Ejecutar',
  },
  rechazada: {
    titleKey: 'anulaciones.transicion.rechazada.title',
    title: 'Rechazar anulación',
    descriptionKey: 'anulaciones.transicion.rechazada.description',
    description: 'Esta acción rechaza la anulación de forma definitiva.',
    submitKey: 'anulaciones.transicion.rechazada.submit',
    submit: 'Rechazar',
  },
};

function mapTransicionError(err: unknown): { message: string; blocked: boolean } {
  if (err instanceof IllegalTransitionError) return { message: err.message, blocked: true };
  if (err instanceof PermissionDeniedError) return { message: err.message, blocked: false };
  if (err instanceof TenantScopeViolationError) return { message: err.message, blocked: false };
  return { message: err instanceof Error ? err.message : 'Error desconocido', blocked: false };
}

export function TransicionAnulacionModal({
  uuidAnulacion,
  estadoDestino,
  open,
  onClose,
  onTransicionada,
}: TransicionAnulacionModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);

  const form = useForm<AnulacionTransicionFormInput>({
    resolver: zodResolver(anulacionTransicionFormSchema),
    defaultValues: { motivo: '' },
  });

  const copy = ACCION_COPY[estadoDestino];

  function resetAndClose(): void {
    form.reset({ motivo: '' });
    setSubmitError(null);
    setBlocked(false);
    onClose();
  }

  async function onSubmit(values: AnulacionTransicionFormInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const updated = await transicionarAnulacion(uuidAnulacion, estadoDestino, values.motivo);
      onTransicionada(updated);
      resetAndClose();
    } catch (err) {
      const mapped = mapTransicionError(err);
      setSubmitError(mapped.message);
      setBlocked(mapped.blocked);
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) resetAndClose();
      }}
      contentProps={{ 'data-testid': 'transicion-anulacion-modal' } as HTMLAttributes<HTMLDivElement>}
    >
      <Card className="w-full max-w-lg shadow-elevation-3">
        <CardHeader>
          <DialogTitle>{t(copy.titleKey, copy.title)}</DialogTitle>
          <DialogDescription>{t(copy.descriptionKey, copy.description)}</DialogDescription>
        </CardHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
            aria-busy={submitting}
            data-testid="transicion-anulacion-form"
          >
            <CardContent className="space-y-3">
              {submitError !== null && (
                <p
                  role="alert"
                  aria-live="assertive"
                  data-testid="transicion-anulacion-error"
                  className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {submitError}
                </p>
              )}
              <FormField
                control={form.control}
                name="motivo"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="transicion-anulacion-motivo">
                      {t('anulaciones.transicion.motivoLabel', 'Motivo')}
                    </FormLabel>
                    <FormControl>
                      <textarea
                        id="transicion-anulacion-motivo"
                        data-testid="transicion-anulacion-motivo"
                        rows={4}
                        maxLength={2000}
                        disabled={blocked}
                        className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
            <CardFooter className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={resetAndClose}
                disabled={submitting}
                data-testid="transicion-anulacion-cancel"
              >
                {t('common.cancel', 'Cancelar')}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={submitting || blocked}
                data-testid="transicion-anulacion-submit"
              >
                {submitting
                  ? t('anulaciones.transicion.submitting', 'Guardando…')
                  : t(copy.submitKey, copy.submit)}
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </Dialog>
  );
}
