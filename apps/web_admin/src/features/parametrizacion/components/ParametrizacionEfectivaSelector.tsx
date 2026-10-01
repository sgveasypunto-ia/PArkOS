/**
 * `ParametrizacionEfectivaSelector` — HU-F15.1 BR4 shared datepicker.
 *
 * Pure/presentational: receives `value` (`YYYY-MM-DD`) + `onChange` +
 * `onResetHoy`, renders a native date `<input>` (shadcn `Input`, same
 * primitive every other form in this app already uses — no new
 * component/dependency) plus a "Hoy" reset button. Exported standalone so
 * other Fase 15 tabs (Resoluciones, Caja) can mount it against their OWN
 * `useParametrizacionEfectiva()` instance later without depending on
 * `SucursalDetalle.tsx`.
 */
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface ParametrizacionEfectivaSelectorProps {
  /** `YYYY-MM-DD` — the point in time the parent resolves "vigente" against. */
  value: string;
  onChange: (value: string) => void;
  onResetHoy: () => void;
  /** Disambiguates `id`/`data-testid` when more than one instance mounts
   * on the same page (future tabs embedding their own). */
  idPrefix?: string;
}

export function ParametrizacionEfectivaSelector({
  value,
  onChange,
  onResetHoy,
  idPrefix = 'parametrizacion-efectiva',
}: ParametrizacionEfectivaSelectorProps): JSX.Element {
  const { t } = useTranslation();
  const inputId = `${idPrefix}-fecha`;

  return (
    <div
      className="flex flex-wrap items-end gap-2"
      data-testid={`${idPrefix}-selector`}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor={inputId} className="text-xs text-muted-foreground">
          {t('parametrizacion.vigenteEn.label', 'Ver parametrización vigente en')}
        </Label>
        <Input
          id={inputId}
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`${idPrefix}-fecha-input`}
          className="w-44"
        />
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onResetHoy}
        data-testid={`${idPrefix}-hoy`}
      >
        {t('parametrizacion.vigenteEn.hoy', 'Hoy')}
      </Button>
    </div>
  );
}
