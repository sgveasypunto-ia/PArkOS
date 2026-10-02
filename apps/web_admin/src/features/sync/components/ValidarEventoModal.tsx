/**
 * `<ValidarEventoModal />` — HU-F19.6 action modal for approving or
 * rejecting a `validacion_evento` chain tip (CU-07), via the already-real
 * `POST /api/v1/validacion-evento` (implemented in this same worktree,
 * `dian/cloud_router.py::create_validacion_evento`). This component is a
 * thin RHF+Zod form in front of that existing endpoint — it does not
 * reimplement any backend transition logic.
 *
 * Mirrors `alertas/components/DescartarAlertaModal.tsx`'s RHF+Zod shape,
 * but this transition has TWO outcomes instead of one: a radio group
 * picks `validado` vs `rechazado`, and `observaciones` becomes
 * required+non-blank ONLY when `rechazado` is selected (BE:
 * `ValidacionEventoCreate._validar_estado_transicion` — no such
 * requirement for `validado`), enforced client-side by
 * `validarEventoFormSchema`'s `superRefine`.
 *
 * 409 `validacion_evento_transicion_ilegal`
 * (`ValidacionEventoTransicionIlegalError`) is a distinct, expected
 * outcome — a concurrent admin already resolved this same chain tip —
 * so it gets its own clear message instead of the generic error banner
 * text, and `onResuelto` is NOT called (nothing to merge in; the caller
 * should instead revalidate its list on close). Mirrors
 * `AlertaYaResueltaError` handling in `DescartarAlertaModal`.
 *
 * Uses the hand-rolled `<Dialog />` (`@/components/ui/dialog.tsx`),
 * exactly like `DescartarAlertaModal` / `RevocarPairingModal` /
 * `GenerarPairingTokenModal`, to stay on the safe, already-tested
 * focus-trap path.
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
  ValidacionEventoTransicionIlegalError,
  createValidacionEventoTransicion,
} from '../api/validacionEventoApi';
import {
  validarEventoFormSchema,
  type ValidarEventoFormInput,
} from '../api/validacionEventoSchema';

export interface ValidarEventoModalProps {
  /** The uuid of the current chain tip being acted on. */
  uuidValidacionPadre: string;
  open: boolean;
  onClose: () => void;
  onResuelto: (uuid: string) => void;
}

function mapError(err: unknown): { message: string; yaResuelto: boolean } {
  if (err instanceof ValidacionEventoTransicionIlegalError) {
    return { message: err.message, yaResuelto: true };
  }
  return { message: err instanceof Error ? err.message : 'Error desconocido', yaResuelto: false };
}

export function ValidarEventoModal({
  uuidValidacionPadre,
  open,
  onClose,
  onResuelto,
}: ValidarEventoModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [yaResuelto, setYaResuelto] = useState(false);

  const form = useForm<ValidarEventoFormInput>({
    resolver: zodResolver(validarEventoFormSchema),
    defaultValues: { estado: 'validado', observaciones: '' },
  });

  const estado = form.watch('estado');

  function resetAndClose(): void {
    form.reset({ estado: 'validado', observaciones: '' });
    setSubmitError(null);
    setYaResuelto(false);
    onClose();
  }

  async function onSubmit(values: ValidarEventoFormInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { uuid } = await createValidacionEventoTransicion({
        uuidValidacionPadre,
        estado: values.estado,
        observaciones: values.observaciones,
      });
      onResuelto(uuid);
      resetAndClose();
    } catch (err) {
      const mapped = mapError(err);
      setSubmitError(mapped.message);
      setYaResuelto(mapped.yaResuelto);
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
      contentProps={{ 'data-testid': 'validar-evento-modal' } as HTMLAttributes<HTMLDivElement>}
    >
      <Card className="w-full max-w-lg shadow-elevation-3">
        <CardHeader>
          <DialogTitle>{t('sync.validacionEventos.modal.title', 'Validar evento')}</DialogTitle>
          <DialogDescription>
            {t(
              'sync.validacionEventos.modal.description',
              'Aprobá o rechazá este evento recibido. La decisión queda registrada en el historial.',
            )}
          </DialogDescription>
        </CardHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
            aria-busy={submitting}
            data-testid="validar-evento-form"
          >
            <CardContent className="space-y-3">
              {submitError !== null && (
                <p
                  role="alert"
                  aria-live="assertive"
                  data-testid="validar-evento-error"
                  className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {submitError}
                </p>
              )}

              <FormField
                control={form.control}
                name="estado"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('sync.validacionEventos.modal.decisionLabel', 'Decisión')}
                    </FormLabel>
                    <FormControl>
                      <div
                        role="radiogroup"
                        aria-label={t('sync.validacionEventos.modal.decisionLabel', 'Decisión')}
                        className="flex gap-4"
                      >
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            ref={field.ref}
                            type="radio"
                            name={field.name}
                            value="validado"
                            checked={field.value === 'validado'}
                            onChange={() => field.onChange('validado')}
                            onBlur={field.onBlur}
                            disabled={yaResuelto}
                            data-testid="validar-evento-radio-validado"
                          />
                          {t('sync.validacionEventos.modal.validar', 'Validar')}
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="radio"
                            name={field.name}
                            value="rechazado"
                            checked={field.value === 'rechazado'}
                            onChange={() => field.onChange('rechazado')}
                            onBlur={field.onBlur}
                            disabled={yaResuelto}
                            data-testid="validar-evento-radio-rechazado"
                          />
                          {t('sync.validacionEventos.modal.rechazar', 'Rechazar')}
                        </label>
                      </div>
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
                    <FormLabel htmlFor="validar-evento-observaciones">
                      {t('sync.validacionEventos.modal.observacionesLabel', 'Observaciones')}
                      {estado === 'rechazado' && (
                        <span aria-hidden="true" className="text-destructive">
                          {' '}
                          *
                        </span>
                      )}
                    </FormLabel>
                    <FormControl>
                      <textarea
                        id="validar-evento-observaciones"
                        data-testid="validar-evento-observaciones"
                        rows={4}
                        maxLength={2000}
                        disabled={yaResuelto}
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
                data-testid="validar-evento-cancel"
              >
                {t('common.cancel', 'Cancelar')}
              </Button>
              <Button
                type="submit"
                variant={estado === 'rechazado' ? 'destructive' : 'default'}
                disabled={submitting || yaResuelto}
                data-testid="validar-evento-submit"
              >
                {submitting
                  ? t('sync.validacionEventos.modal.submitting', 'Guardando…')
                  : t('sync.validacionEventos.modal.submit', 'Confirmar')}
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </Dialog>
  );
}
