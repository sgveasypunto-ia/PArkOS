/**
 * `VigenteBadge` — badge activo/inactivo para catálogos bi-temporales.
 *
 * Catálogo vigente = `vigente_hasta IS NULL AND estado = 'activo'`.
 * Cualquier otra combinación (cerrado, anulado, en transición) = inactivo.
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';

interface VigenteBadgeProps {
  vigenteHasta: string | null;
  estado: 'activo' | 'inactivo';
}

export function VigenteBadge({ vigenteHasta, estado }: VigenteBadgeProps): JSX.Element {
  const { t } = useTranslation();
  const isActive = estado === 'activo' && vigenteHasta === null;
  return (
    <Badge variant={isActive ? 'default' : 'secondary'} data-testid="vigente-badge">
      {isActive
        ? t('catalogos.vigente', 'Vigente')
        : t('catalogos.noVigente', 'No vigente')}
    </Badge>
  );
}
