/**
 * `<CambiarPasswordForm />` -- presentational counterpart to the
 * must-change branch in ``pages/Login.tsx``.
 *
 * Mirror of web_admin's CambiarPasswordForm -- duplicated (not in
 * @parkos/ui-kit) for the same reason as LoginForm.
 *
 * RNF-022 (WCAG 2.1 AA):
 *   - Field labels via ``htmlFor``/``id``.
 *   - Errors surface in ``role="alert"`` with ``aria-live``.
 *   - Submit button is disabled while pending.
 *
 * HU-F16 must-change enforcement (migration 0065): the operator just
 * authenticated with a temporary credential issued by an admin
 * reset; the login handler returned a 5-minute JWT with
 * ``purpose='must_change'``. This form exchanges it for a real
 * TokenPair.
 */
import { type UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
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
  /**
   * The submit handler. Accepts either:
   *   - a function taking the typed values (RHF's `handleSubmit(values => ...)`);
   *   - the raw form-event handler that RHF's `handleSubmit` returns.
   * We type it permissively because the consumer (the container) wraps
   * the form's `handleSubmit` and we don't want to lock the container
   * into a particular shape.
   */
  onSubmit: (values: CambiarPasswordInput) => void | Promise<void>;
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
          ? t('auth:networkError')
          : t('auth:serverError', { status: errorState.status });

  return (
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
  );
}