/**
 * `<PairingForm />` -- presentational form for the branch pairing
 * (IT-2.8).
 *
 * Mirrors the DEC-F3.1-02 Container/Presentational split: this file
 * is render-only; the container (`<PairingWizard />`) owns the submit
 * handler, the IPC bridge persistence, and the post-pair navigation.
 *
 * Accessibility (RNF-022 WCAG 2.1 AA):
 *   - All inputs labeled with `<FormLabel htmlFor>`.
 *   - Zod errors surface as `<FormMessage role="alert">`.
 *   - The `<input>`s go inside a wrapping `<fieldset disabled>` set by
 *     the container; this component just receives `disabled` for
 *     individual field readability.
 */
import type { UseFormReturn } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

import type { PairingRequestInput } from '../api/pairingSchema';

export interface PairingFormProps {
  form: UseFormReturn<PairingRequestInput>;
  disabled: boolean;
}

export function PairingForm({ form, disabled }: PairingFormProps) {
  const { t } = useTranslation();
  return (
    <>
      <FormField
        control={form.control}
        name="pairing_token"
        render={({ field }) => (
          <FormItem>
            <FormLabel htmlFor="pairing_token">{t('pairing.field.token')}</FormLabel>
            <FormControl>
              <Input
                id="pairing_token"
                data-testid="pairing-field-token"
                placeholder="eyJ..."
                autoComplete="off"
                disabled={disabled}
                {...field}
                value={field.value ?? ''}
              />
            </FormControl>
            <FormDescription>{t('pairing.field.tokenHelp')}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="uuid_sucursal"
        render={({ field }) => (
          <FormItem>
            <FormLabel htmlFor="uuid_sucursal">{t('pairing.field.uuid')}</FormLabel>
            <FormControl>
              <Input
                id="uuid_sucursal"
                data-testid="pairing-field-uuid"
                placeholder="00000000-0000-0000-0000-0000000000b1"
                autoComplete="off"
                disabled={disabled}
                {...field}
                value={field.value ?? ''}
              />
            </FormControl>
            <FormDescription>{t('pairing.field.uuidHelp')}</FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  );
}
