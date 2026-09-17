/**
 * `PlacaInput.tsx` — operator-facing vehicle plate entry field
 * (HU-F6.1, CU-01, T5).
 *
 * Spec scenarios (from `specs/operacion-ingreso.md`):
 *   1. Auto-focus on mount (`useRef<HTMLInputElement>`).
 *   2. Trim + uppercase normalization via F4.1 `detectarTipoVehiculo`.
 *   3. Submit by Enter key (no button click required).
 *   4. Zod regex check (`REGEX_AUTO | REGEX_MOTO`).
 *
 * The form is RHF + Zod (DEC-SUC-06). Schema reuses the canonical
 * F4.1 regexes — we intentionally do NOT pass `detectarTipoVehiculo`
 * to RHF because RHF works better with a sync Zod resolver.
 *
 * `onValidSubmit(placa)` is the ONLY side effect — the parent page
 * (`Principal.tsx`) handles the rest of the flow (active-check,
 * confirm, post, modal).
 *
 * i18n keys reused (already present in `operacion.json` from F6.2
 * and F4.1):
 *   - `placa_formato_invalido` (F4.1) — inline error
 *   - `ingreso_placa_label` (F6.1) — label
 *   - `ingreso_registrar` (F6.1) — submit button text
 */
import { useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';

import { REGEX_AUTO, REGEX_MOTO } from '../../../lib/validation/placa';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';

/**
 * Placa schema — single field, trimmed + uppercased on transform, then
 * matched against the F4.1 regexes (Auto | Moto). The shape is local
 * to the component because RHF requires a literal Zod object schema;
 * the underlying constants live in `lib/validation/placa.ts`.
 */
const placaFormSchema = z.object({
  placa: z
    .string()
    .trim()
    .transform((s) => s.toUpperCase().replace(/\s+/g, ''))
    .refine((s) => REGEX_AUTO.test(s) || REGEX_MOTO.test(s), {
      message: 'placa_formato_invalido',
    }),
});

export type PlacaFormValues = z.infer<typeof placaFormSchema>;

export interface PlacaInputProps {
  /** Called when the operator submits a valid plate (Enter or button). */
  onValidSubmit: (placa: string) => void;
  /** Disable while the parent is processing (e.g. confirming). */
  disabled?: boolean;
  /**
   * Optional pre-fill. When provided AND matching the F4.1 regexes
   * (Auto | Moto), the input value is set on mount so the operator
   * sees the plate and just has to press Enter / "Registrar" once.
   * We DO NOT auto-submit — the operator must confirm explicitly.
   */
  initialValue?: string | null;
}

/**
 * F6.1 plate input — auto-focus on mount, uppercase normalization,
 * Enter-submit, Zod validation against F4.1 regexes.
 */
export function PlacaInput({ onValidSubmit, disabled, initialValue }: PlacaInputProps) {
  const { t } = useTranslation('operacion');
  const inputRef = useRef<HTMLInputElement | null>(null);
  const form = useForm<PlacaFormValues>({
    resolver: zodResolver(placaFormSchema),
    defaultValues: { placa: '' },
    mode: 'onSubmit',
  });

  useEffect(() => {
    // Auto-focus on mount per spec scenario "Plate normalized to
    // uppercase + auto-focused".
    inputRef.current?.focus();
  }, []);

  // Pre-fill on mount only (initialValue is read-once). If the supplied
  // value matches the F4.1 regexes, set it in the form so the operator
  // sees the plate and can submit with one Enter / one click. We do not
  // submit on the operator's behalf — they must confirm.
  useEffect(() => {
    if (!initialValue) return;
    if (!REGEX_AUTO.test(initialValue) && !REGEX_MOTO.test(initialValue)) return;
    form.setValue('placa', initialValue, { shouldValidate: false });
    // Re-focus the input so the operator can immediately press Enter.
    inputRef.current?.focus();
    // form is stable; only re-run if the initialValue changes between
    // mount cycles (the typical case is mount-only, but tests may
    // re-render with different values).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialValue]);

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((values) => onValidSubmit(values.placa))}
        className="space-y-4"
      >
        <FormField
          control={form.control}
          name="placa"
          render={({ field }) => (
            <FormItem>
              <FormLabel htmlFor="placa">
                {t('ingreso_placa_label', { defaultValue: 'Placa' })}
              </FormLabel>
              <FormControl>
                <Input
                  id="placa"
                  ref={(node) => {
                    inputRef.current = node;
                    field.ref(node);
                  }}
                  name={field.name}
                  value={field.value}
                  onBlur={field.onBlur}
                  onChange={(event) => {
                    // DEC-F4.1-02 normalization: trim + uppercase +
                    // strip whitespace at the input boundary so RHF's
                    // Zod refinement always sees a clean string.
                    const normalized = event.target.value
                      .toUpperCase()
                      .replace(/\s+/g, '');
                    field.onChange(normalized);
                  }}
                  placeholder="ABC123"
                  autoComplete="off"
                  autoCapitalize="characters"
                  inputMode="text"
                  maxLength={8}
                  disabled={disabled}
                  aria-describedby="placa-help"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={disabled}>
          {t('ingreso_registrar', { defaultValue: 'Registrar' })}
        </Button>
      </form>
    </Form>
  );
}
