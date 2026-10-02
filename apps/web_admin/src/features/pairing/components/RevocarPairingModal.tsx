/**
 * `<RevocarPairingModal />` — HU-F19.3 revoke actions for a sucursal.
 *
 * Section A "Revocar token de pairing": actionable only when the
 * caller passes a known `pairingTokenUuid` (per BR4, the admin UI only
 * "knows" a token issued from the pairing screen in THIS browser).
 * When unknown, the button renders disabled with explanatory copy
 * instead of silently doing nothing.
 *
 * Section B "Revocar sincronización activa (avanzado)": always
 * available, independent of Section A. This revokes an already-paired
 * device's live sync credential — a DIFFERENT artifact from a pairing
 * token. There is NO backend lookup to auto-discover a branch's
 * current `jwt_kid`/`jwt_uuid`; the admin must know/paste them (e.g.
 * from audit logs).
 *
 * Each section owns its own inline `role=alert` error banner; a
 * failure in one section must not disable the other.
 */
import { useState } from 'react';
import type { HTMLAttributes } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

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
  PairingTokenNotFoundError,
  TenantScopeViolationError,
  revokePairingToken,
  revokeSucursalSync,
} from '../api/pairingApi';

export interface RevocarPairingModalProps {
  sucursalUuid: string;
  sucursalNombre?: string | null;
  pairingTokenUuid: string | null;
  open: boolean;
  onClose: () => void;
  onRevoked: () => void;
}

const revokeSyncFormSchema = z.object({
  jwtKid: z
    .string()
    .min(1, 'El jwt_kid es obligatorio.')
    .max(64, 'El jwt_kid no puede superar 64 caracteres.'),
  jwtUuid: z
    .string()
    .min(1, 'El jwt_uuid es obligatorio.')
    .max(64, 'El jwt_uuid no puede superar 64 caracteres.'),
});

type RevokeSyncFormInput = z.infer<typeof revokeSyncFormSchema>;

function mapRevokeError(err: unknown): string {
  if (err instanceof PairingTokenNotFoundError || err instanceof TenantScopeViolationError) {
    return err.message;
  }
  return err instanceof Error ? err.message : 'Error desconocido';
}

export function RevocarPairingModal({
  sucursalUuid,
  sucursalNombre,
  pairingTokenUuid,
  open,
  onClose,
  onRevoked,
}: RevocarPairingModalProps): JSX.Element | null {
  const { t } = useTranslation();
  const [revokingToken, setRevokingToken] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [revokingSync, setRevokingSync] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const form = useForm<RevokeSyncFormInput>({
    resolver: zodResolver(revokeSyncFormSchema),
    defaultValues: { jwtKid: '', jwtUuid: '' },
  });

  if (!open) return null;

  async function handleRevokeToken(): Promise<void> {
    if (pairingTokenUuid === null) return;
    setRevokingToken(true);
    setTokenError(null);
    try {
      await revokePairingToken(pairingTokenUuid);
      onRevoked();
      onClose();
    } catch (err) {
      setTokenError(mapRevokeError(err));
    } finally {
      setRevokingToken(false);
    }
  }

  async function onSubmitSync(values: RevokeSyncFormInput): Promise<void> {
    setRevokingSync(true);
    setSyncError(null);
    try {
      await revokeSucursalSync(sucursalUuid, {
        jwtKid: values.jwtKid,
        jwtUuid: values.jwtUuid,
      });
      onRevoked();
      onClose();
    } catch (err) {
      setSyncError(mapRevokeError(err));
    } finally {
      setRevokingSync(false);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      contentProps={{ 'data-testid': 'revocar-pairing-modal' } as HTMLAttributes<HTMLDivElement>}
    >
      <Card className="w-full max-w-lg shadow-elevation-3">
        <CardHeader>
          <DialogTitle>{t('pairing.revocar.title', 'Revocar pairing')}</DialogTitle>
          <DialogDescription>{sucursalNombre ?? sucursalUuid}</DialogDescription>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Section A -- revoke the known pairing token */}
          <section
            data-testid="revocar-pairing-token-section"
            className="space-y-2 border-b pb-4"
          >
            <h3 className="text-sm font-semibold">
              {t('pairing.revocar.tokenTitle', 'Revocar token de pairing')}
            </h3>
            {pairingTokenUuid === null && (
              <p
                className="text-sm text-muted-foreground"
                data-testid="revocar-pairing-token-unknown"
              >
                {t(
                  'pairing.revocar.tokenUnknown',
                  'No hay un token conocido para esta sucursal desde este navegador.',
                )}
              </p>
            )}
            {tokenError !== null && (
              <p
                role="alert"
                aria-live="assertive"
                data-testid="revocar-pairing-token-error"
                className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {tokenError}
              </p>
            )}
            <Button
              type="button"
              variant="destructive"
              onClick={() => void handleRevokeToken()}
              disabled={pairingTokenUuid === null || revokingToken}
              data-testid="revocar-pairing-token-confirm"
            >
              {revokingToken
                ? t('pairing.revocar.tokenSubmitting', 'Revocando…')
                : t('pairing.revocar.tokenConfirm', 'Revocar token')}
            </Button>
          </section>

          {/* Section B -- revoke an active sync credential (advanced) */}
          <section data-testid="revocar-pairing-sync-section" className="space-y-3">
            <h3 className="text-sm font-semibold">
              {t('pairing.revocar.syncTitle', 'Revocar sincronización activa (avanzado)')}
            </h3>
            <p className="text-xs text-muted-foreground">
              {t(
                'pairing.revocar.syncHelp',
                'No existe una forma automática de descubrir las credenciales activas de una sucursal pareada. Pegá el jwt_kid y el jwt_uuid (por ejemplo, desde los logs de auditoría) para revocar esa sincronización.',
              )}
            </p>
            {syncError !== null && (
              <p
                role="alert"
                aria-live="assertive"
                data-testid="revocar-pairing-sync-error"
                className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {syncError}
              </p>
            )}
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit(onSubmitSync)}
                noValidate
                className="space-y-3"
                aria-busy={revokingSync}
                data-testid="revocar-pairing-sync-form"
              >
                <FormField
                  control={form.control}
                  name="jwtKid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="revocar-sync-jwt-kid">
                        {t('pairing.revocar.jwtKidLabel', 'jwt_kid')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          id="revocar-sync-jwt-kid"
                          data-testid="revocar-sync-jwt-kid"
                          maxLength={64}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="jwtUuid"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="revocar-sync-jwt-uuid">
                        {t('pairing.revocar.jwtUuidLabel', 'jwt_uuid')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          id="revocar-sync-jwt-uuid"
                          data-testid="revocar-sync-jwt-uuid"
                          maxLength={64}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="flex justify-end">
                  <Button
                    type="submit"
                    variant="destructive"
                    disabled={revokingSync}
                    data-testid="revocar-pairing-sync-submit"
                  >
                    {revokingSync
                      ? t('pairing.revocar.syncSubmitting', 'Revocando…')
                      : t('pairing.revocar.syncConfirm', 'Revocar sincronización')}
                  </Button>
                </div>
              </form>
            </Form>
          </section>
        </CardContent>

        <CardFooter className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            data-testid="revocar-pairing-close"
          >
            {t('common.close', 'Cerrar')}
          </Button>
        </CardFooter>
      </Card>
    </Dialog>
  );
}
