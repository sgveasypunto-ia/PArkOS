/**
 * `<ReimprimirTiquete />` — routed page (HU-F8.3, REQ-OPS-171).
 *
 * Lives at `/facturacion/reimprimir` and mounts inside
 * `<ProtectedRoute>` (App.tsx). The page implements the reimpresión
 * con costo flow on the renderer side, composing two hooks:
 *
 *   - `useReimprimir()` — POST `/api/v1/workflows/reimpresion-ticket
 *     /{uuid_ingreso}/reimprimir` with Idempotency-Key SHA-256 +
 *     motivo Zod pre-validation (`motivo.min(10)`) + 401 auth-clear.
 *   - `useAnularReimpresion()` — POST `/{uuid}/anular` with INSERT-only
 *     chain invariant (F1.11 DEC-TKT-03) + motivo_anulacion Zod.
 *
 * Rendering rules (REQ-OPS-171):
 *   - `role="alertdialog"` on the cobro-consequence confirmation
 *     dialog (WCAG 2.1 AA — alertdialog is the canonical a11y
 *     role for actions with destructive or financial consequences).
 *   - `motivo: z.string().min(10)` RHF + Zod resolver — checked BEFORE
 *     the dialog opens so the operator never sees a 400 round-trip.
 *   - `tipo: 'entrada' | 'salida'` RadioGroup selector (single-page
 *     with tipo selector per proposal §3.1 OD-1 ratified).
 *   - Success card renders uuid_reimpresion + motivo + "Anular"
 *     action that opens a second alertdialog with motivo_anulacion.
 *
 * The page bypasses the existing `<ReimprimirTiqueteSheet />` drawer
 * (F7.x) on purpose — the drawer is a SHORTER flow for the
 * reimpresión gratuita inmediata path (Fase 7). The page is the
 * canonical entry point for the con-costo flow (Fase 8).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

import { useReimprimir } from '../hooks/useReimprimir';
import { useAnularReimpresion } from '../hooks/useAnularReimpresion';
import type { ReimpresionTicketRead } from '../api/reimpresionApi';

const reimprimirFormSchema = z.object({
  uuidIngreso: z.string().uuid('uuid_ingreso_formato_invalido'),
  tipo: z.enum(['entrada', 'salida']),
  motivo: z.string().trim().min(10, 'motivo_muy_corto'),
});
type ReimprimirFormValues = z.infer<typeof reimprimirFormSchema>;

const anularFormSchema = z.object({
  motivo_anulacion: z.string().trim().min(10, 'motivo_anulacion_muy_corto'),
});
type AnularFormValues = z.infer<typeof anularFormSchema>;

export function ReimprimirTiquete(): JSX.Element {
  const { t } = useTranslation('facturacion');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [anularOpen, setAnularOpen] = useState(false);
  const [resultado, setResultado] = useState<ReimpresionTicketRead | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const reimprimir = useReimprimir();
  const anular = useAnularReimpresion();

  const form = useForm<ReimprimirFormValues>({
    resolver: zodResolver(reimprimirFormSchema),
    defaultValues: { uuidIngreso: '', tipo: 'entrada', motivo: '' },
    mode: 'onSubmit',
  });

  const anularForm = useForm<AnularFormValues>({
    resolver: zodResolver(anularFormSchema),
    defaultValues: { motivo_anulacion: '' },
    mode: 'onSubmit',
  });

  const handleConfirmOpen = form.handleSubmit(() => {
    setErrorMsg(null);
    setConfirmOpen(true);
  });

  const handleConfirm = async (): Promise<void> => {
    const values = form.getValues();
    setErrorMsg(null);
    try {
      const out = await reimprimir.trigger({
        uuidIngreso: values.uuidIngreso,
        motivo: values.motivo,
        tipo: values.tipo,
      });
      setResultado(out);
      setConfirmOpen(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'error');
    }
  };

  const handleAnularConfirm = anularForm.handleSubmit(async (values) => {
    if (!resultado) return;
    try {
      await anular.trigger({
        uuidReimpresion: resultado.uuid,
        motivo_anulacion: values.motivo_anulacion,
      });
      setAnularOpen(false);
      // Reset the page to step 1 after a successful anulación
      setResultado(null);
      form.reset();
      anularForm.reset();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'error');
    }
  });

  return (
    <article
      className="mx-auto max-w-2xl space-y-4 p-4"
      data-testid="reimprimir-tiquete-page"
    >
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">
          {t('reimprimir.titulo', { defaultValue: 'Reimprimir tiquete' })}
        </h1>
      </header>

      {errorMsg && (
        <div
          role="alert"
          className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive"
          data-testid="reimprimir-error"
        >
          {errorMsg}
        </div>
      )}

      {resultado === null ? (
        <Form {...form}>
          <form
            onSubmit={handleConfirmOpen}
            className="space-y-4"
            data-testid="reimprimir-form"
          >
            <FormField
              control={form.control}
              name="uuidIngreso"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t('reimprimir.placa.label', { defaultValue: 'UUID ingreso' })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      data-testid="reimprimir-uuid"
                      placeholder="00000000-0000-0000-0000-000000000000"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tipo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t('reimprimir.tipo.label', { defaultValue: 'Tipo de tiquete' })}
                  </FormLabel>
                  <FormControl>
                    <div className="flex gap-4" data-testid="reimprimir-tipo">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="tipo"
                          value="entrada"
                          checked={field.value === 'entrada'}
                          onChange={() => field.onChange('entrada')}
                          data-testid="reimprimir-tipo-entrada"
                        />
                        {t('reimprimir.tipo.entrada', { defaultValue: 'Entrada' })}
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="tipo"
                          value="salida"
                          checked={field.value === 'salida'}
                          onChange={() => field.onChange('salida')}
                          data-testid="reimprimir-tipo-salida"
                        />
                        {t('reimprimir.tipo.salida', { defaultValue: 'Salida' })}
                      </label>
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="motivo"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    {t('reimprimir.motivoLabel', {
                      defaultValue: 'Motivo (mín. 10 caracteres)',
                    })}
                  </FormLabel>
                  <FormControl>
                    <Input
                      data-testid="reimprimir-motivo"
                      placeholder={t('reimprimir.motivoPlaceholder', {
                        defaultValue: 'Describe el motivo',
                      })}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button
              type="submit"
              disabled={reimprimir.isMutating}
              data-testid="reimprimir-confirmar"
            >
              {t('reimprimir.confirmar', { defaultValue: 'Reimprimir' })}
            </Button>
          </form>
        </Form>
      ) : (
        <section
          className="space-y-3 rounded-md border bg-card p-4"
          data-testid="reimprimir-success"
        >
          <h2 className="text-lg font-semibold">
            {t('reimprimir.success.titulo', { defaultValue: 'Reimpresión registrada' })}
          </h2>
          <dl className="space-y-1 text-sm">
            <div>
              <dt className="font-medium">UUID</dt>
              <dd data-testid="reimprimir-success-uuid">{resultado.uuid}</dd>
            </div>
            <div>
              <dt className="font-medium">Motivo</dt>
              <dd>{resultado.motivo}</dd>
            </div>
          </dl>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setAnularOpen(true)}
              data-testid="reimprimir-anular"
            >
              {t('reimprimir.anular.titulo', { defaultValue: 'Anular reimpresión' })}
            </Button>
          </div>
        </section>
      )}

      {/* REQ-OPS-171 — cobro consequence confirmation dialog */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent
          role="alertdialog"
          data-testid="reimprimir-confirm-dialog"
          aria-labelledby="reimprimir-confirm-title"
          aria-describedby="reimprimir-confirm-desc"
        >
          <DialogHeader>
            <DialogTitle id="reimprimir-confirm-title">
              {t('reimprimir.alertdialog.title', { defaultValue: 'Confirmar cobro de reimpresión' })}
            </DialogTitle>
            <DialogDescription id="reimprimir-confirm-desc">
              {t('reimprimir.alertdialog.description', {
                defaultValue:
                  'Esta acción registra un cobro en la factura del ingreso. ¿Desea continuar?',
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmOpen(false)}
              data-testid="reimprimir-cancelar"
            >
              {t('common:cancel', { defaultValue: 'Cancelar' })}
            </Button>
            <Button
              type="button"
              onClick={() => {
                void handleConfirm();
              }}
              disabled={reimprimir.isMutating}
              data-testid="reimprimir-dialog-confirm"
            >
              {t('reimprimir.confirmar', { defaultValue: 'Reimprimir' })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* REQ-OPS-174 — anulación dialog with motivo_anulacion */}
      <Dialog open={anularOpen} onOpenChange={setAnularOpen}>
        <DialogContent
          role="alertdialog"
          data-testid="reimprimir-anular-dialog"
          aria-labelledby="reimprimir-anular-title"
          aria-describedby="reimprimir-anular-desc"
        >
          <DialogHeader>
            <DialogTitle id="reimprimir-anular-title">
              {t('reimprimir.anular.titulo', { defaultValue: 'Anular reimpresión' })}
            </DialogTitle>
            <DialogDescription id="reimprimir-anular-desc">
              {t('reimprimir.anular.descripcion', {
                defaultValue:
                  'La anulación registra una fila nueva en la cadena y no modifica la reimpresión original.',
              })}
            </DialogDescription>
          </DialogHeader>
          <Form {...anularForm}>
            <form onSubmit={handleAnularConfirm} className="space-y-4" data-testid="reimprimir-anular-form">
              <FormField
                control={anularForm.control}
                name="motivo_anulacion"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('reimprimir.anular.motivoLabel', {
                        defaultValue: 'Motivo de anulación (mín. 10 caracteres)',
                      })}
                    </FormLabel>
                    <FormControl>
                      <Input
                        data-testid="reimprimir-anular-motivo"
                        placeholder={t('reimprimir.motivoPlaceholder', {
                          defaultValue: 'Describe el motivo',
                        })}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAnularOpen(false)}
                  data-testid="reimprimir-anular-cancelar"
                >
                  {t('common:cancel', { defaultValue: 'Cancelar' })}
                </Button>
                <Button
                  type="submit"
                  disabled={anular.isMutating}
                  data-testid="reimprimir-anular-confirm"
                >
                  {t('reimprimir.anular.confirmar', { defaultValue: 'Anular' })}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </article>
  );
}
