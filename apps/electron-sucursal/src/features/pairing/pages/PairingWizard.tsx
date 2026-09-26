/**
 * `<PairingWizard />` -- first-boot container for the branch kiosk
 * (IT-2.8, REQ-OP-15).
 *
 * Wire-flow (matches `backend/.../sync_router.py::_PairRequest`):
 *
 *   1. Operator pastes the admin-issued pairing-token into a textarea.
 *   2. Operator enters the branch UUID (or reads it from a config file
 *      / QR-code in a follow-up -- IT-2.8 ships the manual entry).
 *   3. On submit: `postPair({ pairing_token, uuid_sucursal, branch_info })`
 *      -> `sync_jwt` (long-lived, 30 days).
 *   4. The `sync_jwt` is persisted via `window.bridge.authStore.set(
 *      'parkos.sync_jwt', sync_jwt)` so subsequent boots skip the wizard.
 *   5. The wizard navigates to the Login page (or whatever the kiosk's
 *      post-pair entry point is) once the JWT is on disk.
 *
 * Defense in depth: `useAuthStore` (Zustand) is NOT used here --
 * the kiosk doesn't have a user JWT yet. The wizard is pre-auth.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 *   - All inputs labeled with `<FormLabel htmlFor>`.
 *   - Submit blocked by RHF + zodResolver validation; errors surface
 *     via `<FormMessage role="alert">`.
 *   - Network error rendered as `<p role="alert" aria-live="assertive">`.
 */
import { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';

import { PairingForm } from '../components/PairingForm';
import { PairingTokenInvalidError, postPair, type PairResponse } from '../api/pairingApi';
import { pairingRequestSchema, type PairingRequestInput } from '../api/pairingSchema';

type PairingError =
  | null
  | { kind: 'invalid_token'; reason: string }
  | { kind: 'network' }
  | { kind: 'server'; status: number };

export default function PairingWizard(): JSX.Element {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorState, setErrorState] = useState<PairingError>(null);
  const [pairResponse, setPairResponse] = useState<PairResponse | null>(null);

  const form = useForm<PairingRequestInput>({
    resolver: zodResolver(pairingRequestSchema),
    defaultValues: {
      pairing_token: '',
      uuid_sucursal: '',
    },
  });

  const onSubmit = useCallback(async (values: PairingRequestInput) => {
    setIsSubmitting(true);
    setErrorState(null);
    try {
      const resp = await postPair({
        pairing_token: values.pairing_token,
        uuid_sucursal: values.uuid_sucursal,
        branch_info: {
          // Minimal info on first boot; richer telemetry is a follow-up.
          hostname: undefined,
          os: undefined,
          version: undefined,
          endpoint_url: undefined,
        },
      });
      setPairResponse(resp);
      // Persist the long-lived sync-agent- JWT via the existing IPC
      // bridge so subsequent boots skip the wizard.
      if (typeof window !== 'undefined' && window.bridge?.authStore?.set) {
        await window.bridge.authStore.set('parkos.sync_jwt', resp.sync_jwt);
      }
    } catch (err) {
      if (err instanceof PairingTokenInvalidError) {
        setErrorState({ kind: 'invalid_token', reason: err.reason });
      } else {
        const status =
          err instanceof Error && 'status' in err ? ((err as { status?: number }).status ?? 0) : 0;
        setErrorState(status === 0 ? { kind: 'network' } : { kind: 'server', status });
      }
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  if (pairResponse !== null) {
    return (
      <main
        className="flex min-h-screen items-center justify-center bg-background p-4"
        data-testid="page-pairing-success"
      >
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>{t('pairing.success.title')}</CardTitle>
            <CardDescription>{t('pairing.success.body')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              className="w-full"
              onClick={() => void navigate('/login')}
              data-testid="pairing-success-continue"
            >
              {t('pairing.success.continue')}
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  const inlineError =
    errorState === null
      ? null
      : errorState.kind === 'invalid_token'
        ? t('pairing.error.invalidToken', { reason: errorState.reason })
        : errorState.kind === 'network'
          ? t('pairing.error.network')
          : t('pairing.error.server', { status: errorState.status });

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-background p-4"
      data-testid="page-pairing"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('pairing.title')}</CardTitle>
          <CardDescription>{t('pairing.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          {inlineError !== null && (
            <p
              role="alert"
              aria-live="assertive"
              data-testid="pairing-error"
              className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {inlineError}
            </p>
          )}
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="space-y-4"
              noValidate
              aria-busy={isSubmitting}
              data-testid="pairing-form"
            >
              <PairingForm form={form} disabled={isSubmitting} />
              <Button
                type="submit"
                className="w-full"
                disabled={isSubmitting}
                data-testid="pairing-submit"
              >
                {isSubmitting ? t('pairing.submitting') : t('pairing.submit')}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </main>
  );
}
