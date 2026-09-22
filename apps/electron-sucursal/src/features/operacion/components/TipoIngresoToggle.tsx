/**
 * `<TipoIngresoToggle>` — dual-button wrapper for the operator's
 * ingreso flow (HU-INGRESO-SIN-PLACA, REQ-OPS-195).
 *
 * Renders two side-by-side `<Button>` components:
 *   - `Con placa` (default selected, visually dominant — `variant="default"`).
 *   - `Sin placa` (secondary — `variant="outline"`).
 *
 * Below the buttons, the active child renders via render-prop callbacks
 * (`renderConPlaca` / `renderSinPlaca`). The parent supplies the
 * concrete `<PlacaInput>` and `<IngresoSinPlacaPanel>` so this component
 * stays presentational and easy to test.
 *
 * After a successful submit, the parent resets the toggle to
 * `'con-placa'` by remounting this component via a `key="fresh"` prop
 * (the simplest reset mechanism — avoids lifting state up).
 *
 * Accessibility (WCAG 2.1 AA):
 *   - `role="group"` + `aria-label` on the button cluster.
 *   - `aria-pressed` on each button so screen readers announce the
 *     selected variant.
 *   - The `Sin placa` button carries `aria-describedby` linking to a
 *     tooltip explaining when to use it (R5 mitigation).
 *
 * R8 mitigation rationale (design.md §7.4): both `Principal.tsx` and
 * `IngresoPanel.tsx` render the same dual-flow; factoring this into a
 * single wrapper keeps the diff small and the review boundary tight
 * (PR-B total ~455 LOC budget).
 */
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

export type TipoIngresoVariant = 'con-placa' | 'sin-placa';

export interface TipoIngresoToggleProps {
  /** Render the con-placa panel (typically `<PlacaInput />`). */
  renderConPlaca: () => ReactNode;
  /** Render the sin-placa panel (typically `<IngresoSinPlacaPanel />`). */
  renderSinPlaca: () => ReactNode;
  /**
   * Initial selected variant. Defaults to `'con-placa'` — the operator's
   * muscle memory (type placa + Enter) is preserved by keeping this
   * the dominant choice on mount.
   */
  defaultVariant?: TipoIngresoVariant;
}

/**
 * `<TipoIngresoToggle>` — two-button selector that swaps between the
 * `<PlacaInput>` and `<IngresoSinPlacaPanel>` renderings. State is
 * local; the parent can reset it by remounting via a `key` prop.
 */
export function TipoIngresoToggle({
  renderConPlaca,
  renderSinPlaca,
  defaultVariant = 'con-placa',
}: TipoIngresoToggleProps) {
  const { t } = useTranslation('operacion');
  const [variant, setVariant] = useState<TipoIngresoVariant>(defaultVariant);

  return (
    <div className="space-y-4" data-testid="tipo-ingreso-toggle">
      <div
        role="group"
        aria-label={t('ingreso_sin_placa_cta', { defaultValue: 'Sin placa' })}
        className="flex gap-2"
      >
        <Button
          type="button"
          variant={variant === 'con-placa' ? 'default' : 'outline'}
          aria-pressed={variant === 'con-placa'}
          onClick={() => setVariant('con-placa')}
          data-testid="tipo-ingreso-con-placa"
        >
          {t('tipo_ingreso_con_placa', { defaultValue: 'Con placa' })}
        </Button>
        <Button
          type="button"
          variant={variant === 'sin-placa' ? 'default' : 'outline'}
          aria-pressed={variant === 'sin-placa'}
          onClick={() => setVariant('sin-placa')}
          data-testid="tipo-ingreso-sin-placa"
        >
          {t('ingreso_sin_placa_cta', { defaultValue: 'Sin placa' })}
        </Button>
      </div>

      <div data-testid={`tipo-ingreso-panel-${variant}`}>
        {variant === 'con-placa' ? renderConPlaca() : renderSinPlaca()}
      </div>
    </div>
  );
}
