/**
 * `TipoVehiculoCell` — resuelve el uuid de un tipo de vehículo a su nombre
 * para la columna "Tipo de vehículo" del catálogo de planes. `null` (sin
 * tipo) se muestra como "Cualquiera" (PT-2).
 */
import { useTranslation } from 'react-i18next';

import { useCatalogList } from '../hooks/useCatalogList';

export function TipoVehiculoCell({ uuid }: { uuid: string | null }): JSX.Element {
  const { t } = useTranslation();
  const { rows } = useCatalogList('tipos-vehiculo');
  if (uuid === null) {
    return <span>{t('catalogos.tipoVehiculoCualquiera', 'Cualquiera')}</span>;
  }
  const row = rows.find((r) => r.uuid === uuid);
  return <span>{row ? String(row.tipo ?? '') : '—'}</span>;
}
