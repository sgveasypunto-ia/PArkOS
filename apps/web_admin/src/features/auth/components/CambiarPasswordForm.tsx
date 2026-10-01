/**
 * `<CambiarPasswordForm />` -- presentational counterpart to the
 * `<CambiarPasswordForm />` logic owned by ``pages/Login.tsx``.
 *
 * Same Container/Presentational split as ``LoginForm``: the container
 * owns the submit lifecycle (POST /auth/cambiar-password, token storage,
 * redirect), this component owns the inputs, layout, and a11y labels.
 *
 * Why a separate form rather than reusing ``LoginForm``:
 *   - Single field (new password), no email -- the identity is in the
 *     temp token, so re-asking the email is friction.
 *   - Must confirm the new password twice (mirrors common password-
 *     change UX; the BE does NOT verify a confirmation, just the
 *     length/character class of the password itself).
 *   - On any failure (401 invalid_temporary_token, network) the
 *     container routes the operator back to the normal login form.
 *
 * RNF-022 (WCAG 2.1 AA):
 *   - Field labels via ``htmlFor``/``id``.
 *   - Errors surface in ``role="alert"`` with ``aria-live``.
 *   - Submit button is disabled while pending.
 */
import { type UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import type { CambiarPasswordInput } from '../api/cambiarPasswordSchema';

export type CambiarPasswordErrorState =
  | null
  | { kind: 'expired' }
  | { kind: 'network' }
  | { kind: 'server'; status: number };

export interface CambiarPasswordFormProps {
  form: UseFormReturn<CambiarPasswordInput>;
  onSubmit: (values: CambiarPasswordInput) => void;
  onCancel: () => void;
  isSubmitting: boolean;
  errorState: CambiarPasswordErrorState;
}

export function CambiarPasswordForm({
  form,
  onSubmit,
  onCancel,
  isSubmitting,
  errorState,
}: CambiarPasswordFormProps): JSX.Element {
  const { t } = useTranslation();
  const errorMessage =
    errorState === null
      ? null
      : errorState.kind === 'expired'
        ? t('mustChangePassword.errors.expired')
        : errorState.kind === 'network'
          ? t('auth.networkError')
          : t('auth.serverError', { status: errorState.status });

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-background p-4"
      data-testid="page-must-change-password"
    >
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('mustChangePassword.title')}</CardTitle>
          <CardDescription>{t('mustChangePassword.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="space-y-4"
              noValidate
              aria-describedby={errorMessage ? 'change-password-error' : undefined}
            >
              {errorMessage !== null && (
                <p
                  id="change-password-error"
                  role="alert"
                  aria-live="assertive"
                  data-testid="change-password-error"
                  className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm font-medium text-destructive"
                >
                  {errorMessage}
                </p>
              )}

              <fieldset disabled={isSubmitting} className="space-y-4">
                <FormField
                  control={form.control}
                  name="new_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="new_password">
                        {t('mustChangePassword.fields.newPassword')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          id="new_password"
                          type="password"
                          autoComplete="new-password"
                          data-testid="change-password-new"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="confirm_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel htmlFor="confirm_password">
                        {t('mustChangePassword.fields.confirmPassword')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          id="confirm_password"
                          type="password"
                          autoComplete="new-password"
                          data-testid="change-password-confirm"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex items-center gap-2">
                  <Button
                    type="submit"
                    className="flex-1"
                    disabled={isSubmitting}
                    data-testid="change-password-submit"
                  >
                    {isSubmitting
                      ? t('mustChangePassword.submitting')
                      : t('mustChangePassword.submit')}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={onCancel}
                    disabled={isSubmitting}
                    data-testid="change-password-cancel"
                  >
                    {t('mustChangePassword.cancel')}
                  </Button>
                </div>
              </fieldset>
            </form>
          </Form>
        </CardContent>
      </Card>
    </main>
  );
}