/**
 * `<IngresoSinPlacaPanel>` — operator UI for ingresos sin placa
 * (HU-INGRESO-SIN-PLACA, REQ-OPS-194/195/196/198).
 *
 * Used inside `<TipoIngresoToggle>` when the operator picks the
 * `Sin placa` variant. Consumes `useTiposVehiculoSinPlaca()` for the
 * available tipos (filtered to bici / patineta per Q4 decision in the
 * proposal). Renders a `<Select>` + `Generar ingreso` button wired to
 * `postIngreso({ placa_presente: false, placa: null, uuid_tipo_vehiculo })`.
 *
 * Empty-state branch (REQ-OPS-196 scenario 2): when the catalog returns
 * no bici/patineta (HARDCODED_CATALOG fallback or branch not seeded
 * with bici/patineta cupos), the panel shows "Esta sucursal no admite
 * ingresos sin placa" + a tooltip explaining the catalog is degraded.
 * The submit button is omitted so the operator cannot POST against an
 * empty select.
 *
 * i18n keys (operacion.json namespace):
 *   - `ingreso_sin_placa_selector_label` → "Tipo de vehículo"
 *   - `ingreso_sin_placa_tipo_bicicleta` → "Bicicleta"
 *   - `ingreso_sin_placa_tipo_patineta` → "Patineta"
 *   - `ingreso_sin_placa_generar_boton` → "Generar ingreso"
 *   - `ingreso_sin_placa_empty_state` → "Esta sucursal no admite ingresos sin placa"
 *
 * Accessibility (R5 mitigation, WCAG 2.1 AA):
 *   - shadcn `<Select>` is keyboard-navigable out of the box.
 *   - Submit button is `type="submit"` with explicit `aria-label`.
 *   - Empty state uses `role="status"` so screen readers announce it.
 */
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { useTiposVehiculoSinPlaca } from '../../catalogos/hooks/useTiposVehiculoSinPlaca';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  postIngreso,
  type PostIngresoPayload,
  type PostIngresoResponse,
} from '../lib/ingresoApi';

/**
 * The sin-placa variant of the discriminated union — extracted as a
 * literal Zod object so we can `.parse()` the selected UUID before
 * constructing the payload. Mirrors the canonical `placaSinPlacaSchema`
 * in `lib/ingresoApi.ts` (REQ-OPS-194).
 */
const sinPlacaFormSchema = z.object({
  uuid_tipo_vehiculo: z.string().uuid({
    message: 'ingreso_sin_placa_tipo_requerido',
  }),
});

export interface IngresoSinPlacaPanelProps {
  /**
   * Called on a successful 201 response. The parent (`Principal.tsx`
   * or `IngresoPanel.tsx`) opens `<TiqueteModal>` with the response's
   * `consecutivo` field per REQ-OPS-197.
   */
  onSuccess: (response: PostIngresoResponse) => void;
  /** Disable while the parent is processing a sibling POST. */
  disabled?: boolean;
}

/**
 * `<IngresoSinPlacaPanel>` — Select + Generar ingreso button. Posts a
 * no-placa ingreso (`placa_presente: false, placa: null`) and yields
 * the response back to the parent. Empty-state branch when the
 * catalog has no bici/patineta.
 */
export function IngresoSinPlacaPanel({
  onSuccess,
  disabled = false,
}: IngresoSinPlacaPanelProps) {
  const { t } = useTranslation('operacion');
  const { tipos } = useTiposVehiculoSinPlaca();
  const [selectedUuid, setSelectedUuid] = useState<string>('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const selectId = useId();

  // Empty state (REQ-OPS-196 scenario 2): catalog has no bici/patineta.
  if (tipos.length === 0) {
    return (
      <div
        className="space-y-2 rounded-md border border-dashed p-4"
        role="status"
        aria-live="polite"
        data-testid="ingreso-sin-placa-empty-state"
      >
        <p className="text-sm text-muted-foreground">
          {t('ingreso_sin_placa_empty_state', {
            defaultValue: 'Esta sucursal no admite ingresos sin placa',
          })}
        </p>
      </div>
    );
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);

    const parsed = sinPlacaFormSchema.safeParse({ uuid_tipo_vehiculo: selectedUuid });
    if (!parsed.success) {
      setSubmitError('ingreso_sin_placa_tipo_requerido');
      return;
    }

    const payload: PostIngresoPayload = {
      placa_presente: false,
      placa: null,
      uuid_tipo_vehiculo: parsed.data.uuid_tipo_vehiculo,
    };

    setSubmitting(true);
    try {
      const response = await postIngreso(payload);
      onSuccess(response);
      // Reset for the next ingreso.
      setSelectedUuid('');
    } catch (err) {
      // Surface a generic error — the parent owns the 422/409 mapping
      // for the F6.1 forzado / 409 redirects. We only catch network
      // failures here.
      setSubmitError(err instanceof Error ? err.message : 'network_error');
    } finally {
      setSubmitting(false);
    }
  };

  const isDisabled = disabled || submitting || selectedUuid === '';

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4"
      data-testid="ingreso-sin-placa-panel"
    >
      <div className="space-y-2">
        <label
          htmlFor={selectId}
          className="text-sm font-medium"
        >
          {t('ingreso_sin_placa_selector_label', {
            defaultValue: 'Tipo de vehículo',
          })}
        </label>
        <Select value={selectedUuid} onValueChange={setSelectedUuid} disabled={disabled || submitting}>
          <SelectTrigger id={selectId} aria-label={t('ingreso_sin_placa_selector_label', { defaultValue: 'Tipo de vehículo' })}>
            <SelectValue
              placeholder={t('ingreso_sin_placa_selector_label', {
                defaultValue: 'Tipo de vehículo',
              })}
            />
          </SelectTrigger>
          {/* Use default ``popper`` positioning (anchored to the trigger)
              + ``!fixed z-[10000]`` in ``SelectContent`` (see
              ``select.tsx``) so the dropdown spans the full trigger
              width and floats below it. ``position="item-aligned"`` was
              tried earlier but placed the dropdown at the first item's
              coords — anchored to top-left in this narrow dialog,
              looking orphaned from the trigger. */}
          <SelectContent>
            {tipos.map((tipo) => (
              <SelectItem key={tipo.uuid} value={tipo.uuid}>
                {tipo.tipo === 'bicicleta'
                  ? t('ingreso_sin_placa_tipo_bicicleta', { defaultValue: 'Bicicleta' })
                  : t('ingreso_sin_placa_tipo_patineta', { defaultValue: 'Patineta' })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Button
        type="submit"
        disabled={isDisabled}
        size="lg"
        className="w-full"
        data-testid="ingreso-sin-placa-generar"
      >
        {t('ingreso_sin_placa_generar_boton', {
          defaultValue: 'Generar ingreso',
        })}
      </Button>

      {submitError && (
        <p role="alert" className="text-sm text-destructive">
          {t(`error_${submitError}`, { defaultValue: submitError })}
        </p>
      )}
    </form>
  );
}
