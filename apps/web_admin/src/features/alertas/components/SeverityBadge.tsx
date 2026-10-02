/**
 * `SeverityBadge` -- badge for the `prod.alert_types.severity`
 * vocabulary (`critical | warning | info`). Follows the same
 * status-vs-categorical separation documented in
 * `catalogos/components/VigenteBadge.tsx`: no hardcoded colors, only
 * the semantic tokens `@/components/ui/badge.tsx` already exposes.
 *
 * BR4: `severity === null` (either the BE carried it as `null` -- no
 * `alert_types` row for `tipo_alerta` -- or the field is entirely
 * absent, the single-item detail shape) renders "—", NOT an error and
 * NOT a 4th color.
 */
import { useTranslation } from 'react-i18next';

import { Badge, type BadgeProps } from '@/components/ui/badge';

import type { AlertaSeverity } from '../api/alertasSchema';

export interface SeverityBadgeProps {
  severity: AlertaSeverity | null | undefined;
}

const SEVERITY_BADGE: Record<
  AlertaSeverity,
  { labelKey: string; fallback: string; variant: NonNullable<BadgeProps['variant']> }
> = {
  critical: { labelKey: 'alertas.severity.critical', fallback: 'Crítica', variant: 'destructive' },
  warning: { labelKey: 'alertas.severity.warning', fallback: 'Advertencia', variant: 'warning' },
  info: { labelKey: 'alertas.severity.info', fallback: 'Informativa', variant: 'outline' },
};

export function SeverityBadge({ severity }: SeverityBadgeProps): JSX.Element {
  const { t } = useTranslation();

  if (severity === null || severity === undefined) {
    return (
      <Badge variant="outline" data-testid="severity-badge-none">
        {t('alertas.severity.none', '—')}
      </Badge>
    );
  }

  const badge = SEVERITY_BADGE[severity];
  return (
    <Badge variant={badge.variant} data-testid={`severity-badge-${severity}`}>
      {t(badge.labelKey, badge.fallback)}
    </Badge>
  );
}
