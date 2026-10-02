/**
 * `<DescartarAlertaModal />` -- HU-F19.5 confirmation modal for
 * discarding/resolving an alerta via the ALREADY-REAL HU-F19.4
 * `POST /workflows/alerta/{uuid}/descartar` (PR #64, merged to `dev`).
 * This component is a thin RHF+Zod form in front of that existing
 * endpoint -- it does not reimplement any backend transition logic.
 *
 * `observaciones` is mandatory (BE: `min_length=1` + `strip_whitespace`)
 * -- the submit button stays disabled until RHF's zodResolver validates
 * a non-blank value, mirroring the Zod-gated submit on
 * `pairing/components/GenerarPairingTokenModal.tsx`.
 *
 * 409 `alerta_ya_resuelta` (`AlertaYaResueltaError`) is a distinct,
 * expected outcome -- a concurrent actor resolved the alert first -- so
 * it gets its own clear message instead of the generic error banner
 * text, and `onDescartada` is NOT called (nothing to refresh into; the
 * caller should instead revalidate its list/detail on close).
 *
 * Uses the hand-rolled `<Dialog />` (`@/components/ui/dialog.tsx`) --
 * its focus-trap fix (effect depends on `open` alone, reads
 * `onOpenChange` through a ref) is NOT touched here; this form has 1
 * field, so the bug it fixed (losing focus past the first field on
 * every keystroke) was never reachable from a single-field form, but
 * the component is used exactly like `RevocarPairingModal` /
 * `GenerarPairingTokenModal` to stay on the safe, already-tested path.
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
  AlertaYaResueltaError,
  TenantScopeViolationError,
  descartarAlerta,
} from '../api/alertasApi';
import {
  alertaDescartarFormSchema,
  type AlertaDescartarFormInput,
  type AlertaDetailRead,
} from '../api/alertasSchema';

export interface DescartarAlertaModalProps {
  uuidAlerta: string;
  open: boolean;
  onClose: () => void;
  onDescartada: (updated: AlertaDetailRead) => void;
}

function mapDescartarError(err: unknown): { message: string; yaResuelta: boolean } {
  if (err instanceof AlertaYaResueltaError) {
    return { message: err.message, yaResuelta: true };
  }
  if (err instanceof TenantScopeViolationError) {
    return { message: err.message, yaResuelta: false };
  }
  return { message: err instanceof Error ? err.message : 'Error desconocido', yaResuelta: false };
}

export function DescartarAlertaModal({
  uuidAlerta,
  open,
  onClose,
  onDescartada,
}: DescartarAlertaModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [yaResuelta, setYaResuelta] = useState(false);

  const form = useForm<AlertaDescartarFormInput>({
    resolver: zodResolver(alertaDescartarFormSchema),
    defaultValues: { observaciones: '' },
  });

  function resetAndClose(): void {
    form.reset({ observaciones: '' });
    setSubmitError(null);
    setYaResuelta(false);
    onClose();
  }

  async function onSubmit(values: AlertaDescartarFormInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const updated = await descartarAlerta(uuidAlerta, values.observaciones);
      onDescartada(updated);
      resetAndClose();
    } catch (err) {
      const mapped = mapDescartarError(err);
      setSubmitError(mapped.message);
      setYaResuelta(mapped.yaResuelta);
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
      contentProps={{ 'data-testid': 'descartar-alerta-modal' } as HTMLAttributes<HTMLDivElement>}
    >
      <Card className="w-full max-w-lg shadow-elevation-3">
        <CardHeader>
          <DialogTitle>{t('alertas.descartar.title', 'Descartar alerta')}</DialogTitle>
          <DialogDescription>
            {t(
              'alertas.descartar.description',
              'Esta acción resuelve la alerta de forma definitiva. Las observaciones quedan registradas en el historial.',
            )}
          </DialogDescription>
        </CardHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
            aria-busy={submitting}
            data-testid="descartar-alerta-form"
          >
            <CardContent className="space-y-3">
              {submitError !== null && (
                <p
                  role="alert"
                  aria-live="assertive"
                  data-testid="descartar-alerta-error"
                  className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {submitError}
                </p>
              )}
              <FormField
                control={form.control}
                name="observaciones"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="descartar-alerta-observaciones">
                      {t('alertas.descartar.observacionesLabel', 'Observaciones')}
                    </FormLabel>
                    <FormControl>
                      <textarea
                        id="descartar-alerta-observaciones"
                        data-testid="descartar-alerta-observaciones"
                        rows={4}
                        maxLength={2000}
                        disabled={yaResuelta}
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
                data-testid="descartar-alerta-cancel"
              >
                {t('common.cancel', 'Cancelar')}
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={submitting || yaResuelta}
                data-testid="descartar-alerta-submit"
              >
                {submitting
                  ? t('alertas.descartar.submitting', 'Descartando…')
                  : t('alertas.descartar.submit', 'Descartar')}
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </Dialog>
  );
}
