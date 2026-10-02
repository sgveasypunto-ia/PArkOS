/**
 * `<TransicionReclamoModal />` -- HU-F20.3 confirmation modal for
 * advancing a reclamo's chain via
 * `POST /workflows/reclamos/{uuid}/transicion`. Mirrors
 * `TransicionAnulacionModal.tsx` 1:1.
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
  transicionarReclamo,
} from '../api/reclamosApi';
import {
  reclamoTransicionFormSchema,
  type ReclamoEstado,
  type ReclamoRead,
  type ReclamoTransicionFormInput,
} from '../api/reclamosSchema';

export interface TransicionReclamoModalProps {
  uuidReclamo: string;
  estadoDestino: Exclude<ReclamoEstado, 'recibido'>;
  open: boolean;
  onClose: () => void;
  onTransicionada: (updated: ReclamoRead) => void;
}

const ACCION_COPY: Record<
  Exclude<ReclamoEstado, 'recibido'>,
  { titleKey: string; title: string; descriptionKey: string; description: string; submitKey: string; submit: string }
> = {
  en_investigacion: {
    titleKey: 'reclamos.transicion.enInvestigacion.title',
    title: 'Tomar reclamo en revisión',
    descriptionKey: 'reclamos.transicion.enInvestigacion.description',
    description: 'Pasa el reclamo a investigación.',
    submitKey: 'reclamos.transicion.enInvestigacion.submit',
    submit: 'Tomar en revisión',
  },
  resuelto: {
    titleKey: 'reclamos.transicion.resuelto.title',
    title: 'Resolver reclamo',
    descriptionKey: 'reclamos.transicion.resuelto.description',
    description: 'Marca el reclamo como resuelto de forma definitiva.',
    submitKey: 'reclamos.transicion.resuelto.submit',
    submit: 'Resolver',
  },
  rechazado: {
    titleKey: 'reclamos.transicion.rechazado.title',
    title: 'Rechazar reclamo',
    descriptionKey: 'reclamos.transicion.rechazado.description',
    description: 'Rechaza el reclamo de forma definitiva.',
    submitKey: 'reclamos.transicion.rechazado.submit',
    submit: 'Rechazar',
  },
};

function mapTransicionError(err: unknown): { message: string; blocked: boolean } {
  if (err instanceof IllegalTransitionError) return { message: err.message, blocked: true };
  if (err instanceof PermissionDeniedError) return { message: err.message, blocked: false };
  if (err instanceof TenantScopeViolationError) return { message: err.message, blocked: false };
  return { message: err instanceof Error ? err.message : 'Error desconocido', blocked: false };
}

export function TransicionReclamoModal({
  uuidReclamo,
  estadoDestino,
  open,
  onClose,
  onTransicionada,
}: TransicionReclamoModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);

  const form = useForm<ReclamoTransicionFormInput>({
    resolver: zodResolver(reclamoTransicionFormSchema),
    defaultValues: { motivo: '' },
  });

  const copy = ACCION_COPY[estadoDestino];

  function resetAndClose(): void {
    form.reset({ motivo: '' });
    setSubmitError(null);
    setBlocked(false);
    onClose();
  }

  async function onSubmit(values: ReclamoTransicionFormInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const updated = await transicionarReclamo(uuidReclamo, estadoDestino, values.motivo);
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
      contentProps={{ 'data-testid': 'transicion-reclamo-modal' } as HTMLAttributes<HTMLDivElement>}
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
            data-testid="transicion-reclamo-form"
          >
            <CardContent className="space-y-3">
              {submitError !== null && (
                <p
                  role="alert"
                  aria-live="assertive"
                  data-testid="transicion-reclamo-error"
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
                    <FormLabel htmlFor="transicion-reclamo-motivo">
                      {t('reclamos.transicion.motivoLabel', 'Motivo')}
                    </FormLabel>
                    <FormControl>
                      <textarea
                        id="transicion-reclamo-motivo"
                        data-testid="transicion-reclamo-motivo"
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
                data-testid="transicion-reclamo-cancel"
              >
                {t('common.cancel', 'Cancelar')}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={submitting || blocked}
                data-testid="transicion-reclamo-submit"
              >
                {submitting
                  ? t('reclamos.transicion.submitting', 'Guardando…')
                  : t(copy.submitKey, copy.submit)}
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </Dialog>
  );
}
