/**
 * `<GenerarPairingTokenModal />` — HU-F19.3 two-step modal: step 1 is
 * a `ttlHours` form, step 2 reveals the freshly-minted plaintext
 * pairing token (shown ONCE — the backend never returns it again).
 *
 * Structural pattern reused verbatim from the now-retired
 * `features/sucursales/components/PairingTokenDialog.tsx`: the
 * hand-rolled `<Dialog />` + `<Card>` layout, `DialogTitle` /
 * `DialogDescription`, a `role=status aria-live=polite` announcement
 * for the copy action, and `<code aria-label="Pairing token">` for
 * the token value itself.
 *
 * BR1 (hard requirement): once in the reveal step, the admin MUST
 * copy the token before closing — it can never be retrieved again
 * afterwards. While `copied === false`, every dismiss path (the
 * Dialog's own Escape / backdrop-click `onOpenChange`, and the
 * visible "Cerrar" button) is a no-op; only a successful
 * `navigator.clipboard.writeText` flips the gate open.
 *
 * QR: intentionally NOT implemented. No QR-generation library exists
 * in this repo's dependency set (`apps/web_admin/package.json` and its
 * lockfile both checked — confirmed absent), and the HU marks QR as
 * optional. Adding a new dependency for an optional nicety is
 * disproportionate for this change; a future PR can pick it up
 * deliberately.
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
import { Input } from '@/components/ui/input';

import {
  InvalidTtlHoursError,
  PairingTokenRateLimitedError,
  TenantScopeViolationError,
  issuePairingToken,
} from '../api/pairingApi';
import {
  pairingTokenIssueFormSchema,
  type PairingTokenIssueFormInput,
  type PairingTokenIssueResponse,
} from '../api/pairingSchema';

export interface GenerarPairingTokenModalProps {
  sucursalUuid: string;
  sucursalNombre?: string | null;
  open: boolean;
  onClose: () => void;
  onIssued: (resp: PairingTokenIssueResponse) => void;
}

function mapIssueError(err: unknown): string {
  if (
    err instanceof InvalidTtlHoursError ||
    err instanceof PairingTokenRateLimitedError ||
    err instanceof TenantScopeViolationError
  ) {
    return err.message;
  }
  return err instanceof Error ? err.message : 'Error desconocido';
}

export function GenerarPairingTokenModal({
  sucursalUuid,
  sucursalNombre,
  open,
  onClose,
  onIssued,
}: GenerarPairingTokenModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [issued, setIssued] = useState<PairingTokenIssueResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const form = useForm<PairingTokenIssueFormInput>({
    resolver: zodResolver(pairingTokenIssueFormSchema),
    defaultValues: { ttlHours: 24 },
  });

  function resetAndClose(): void {
    setIssued(null);
    setCopied(false);
    setSubmitError(null);
    form.reset({ ttlHours: 24 });
    onClose();
  }

  /** BR1 gate: every dismiss path routes through here. */
  function attemptClose(): void {
    if (issued !== null && !copied) return;
    resetAndClose();
  }

  async function onSubmit(values: PairingTokenIssueFormInput): Promise<void> {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const resp = await issuePairingToken({
        uuidSucursal: sucursalUuid,
        ttlHours: values.ttlHours,
      });
      setIssued(resp);
      onIssued(resp);
    } catch (err) {
      setSubmitError(mapIssueError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopy(): Promise<void> {
    if (issued === null) return;
    try {
      await navigator.clipboard.writeText(issued.token);
      setCopied(true);
    } catch {
      // Clipboard blocked (e.g. insecure context) -- the admin can
      // still select-and-copy manually from the <code> element below.
      // `copied` stays false on purpose, so the BR1 close gate stays shut.
    }
  }

  if (!open) return null;

  const closeCaption = t(
    'pairing.generar.copyWarning',
    'Copiá el token antes de cerrar — no podrás volver a verlo.',
  );

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) attemptClose();
      }}
      contentProps={
        { 'data-testid': 'generar-pairing-token-modal' } as HTMLAttributes<HTMLDivElement>
      }
    >
      <Card className="w-full max-w-md shadow-elevation-3">
        <CardHeader>
          <DialogTitle>{t('pairing.generar.title', 'Generar token de pairing')}</DialogTitle>
          <DialogDescription>
            {issued === null
              ? t('pairing.generar.description', 'Definí cuánto tiempo será válido el token.')
              : t('pairing.generar.revealDescription', closeCaption)}
          </DialogDescription>
        </CardHeader>

        {issued === null ? (
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              noValidate
              aria-busy={submitting}
              data-testid="generar-pairing-token-form"
            >
              <CardContent className="space-y-3">
                {sucursalNombre !== undefined && sucursalNombre !== null && (
                  <p className="text-sm text-muted-foreground">{sucursalNombre}</p>
                )}
                {submitError !== null && (
                  <p
                    role="alert"
                    aria-live="assertive"
                    data-testid="generar-pairing-token-error"
                    className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                  >
                    {submitError}
                  </p>
                )}
                <FormField
                  control={form.control}
                  name="ttlHours"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="pairing-ttl-hours">
                        {t('pairing.generar.ttlLabel', 'Horas de validez (1-168)')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          id="pairing-ttl-hours"
                          data-testid="pairing-ttl-hours"
                          type="number"
                          min={1}
                          max={168}
                          {...field}
                          onChange={(e) => field.onChange(e.target.valueAsNumber)}
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
                  onClick={attemptClose}
                  disabled={submitting}
                  data-testid="generar-pairing-token-cancel"
                >
                  {t('common.cancel', 'Cancelar')}
                </Button>
                <Button
                  type="submit"
                  disabled={submitting}
                  data-testid="generar-pairing-token-submit"
                >
                  {submitting
                    ? t('pairing.generar.submitting', 'Generando…')
                    : t('pairing.generar.submit', 'Generar token')}
                </Button>
              </CardFooter>
            </form>
          </Form>
        ) : (
          <>
            <CardContent className="space-y-3">
              <code
                data-testid="pairing-token-value"
                aria-label="Pairing token"
                className="block break-all rounded-md border bg-muted p-3 font-mono text-xs"
              >
                {issued.token}
              </code>
              <p
                role="status"
                aria-live="polite"
                data-testid="generar-pairing-token-copied-status"
                className="text-xs text-muted-foreground"
              >
                {copied ? t('pairing.generar.copied', 'Token copiado al portapapeles.') : closeCaption}
              </p>
            </CardContent>
            <CardFooter className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={attemptClose}
                disabled={!copied}
                title={copied ? undefined : closeCaption}
                data-testid="generar-pairing-token-close"
              >
                {t('common.close', 'Cerrar')}
              </Button>
              <Button
                type="button"
                onClick={() => void handleCopy()}
                data-testid="generar-pairing-token-copy"
              >
                {copied
                  ? t('pairing.generar.copiedShort', 'Copiado')
                  : t('pairing.generar.copy', 'Copiar')}
              </Button>
            </CardFooter>
          </>
        )}
      </Card>
    </Dialog>
  );
}
