/**
 * `EmpresaBitacoraTab` — tab "Bitácora" del singleton Empresa
 * (HU-F15.2 de `plan.md:3537`).
 *
 * El endpoint canónico de auditoría (`GET /api/v1/admin/audit/log`)
 * filtra por `uuid_sucursal` requerido (`schemas/log_transaccional.py`
 * línea 22) — Empresa es un singleton tenant-global sin
 * `uuid_sucursal`, así que no encaja en ese endpoint. La
 * integración con la API de bitácora de Empresa queda para Fase 20
 * (donde también se reutilizará el `HashChainStatus` que ya está
 * en `src/components/HashChainStatus.tsx`).
 *
 * Por ahora este tab muestra un placeholder honesto que:
 *   1. Avisa que la integración con la API de bitácora está
 *      pendiente (con un testid que pinea la expectativa para que
 *      el PR de Fase 20 la cambie explícitamente).
 *   2. Muestra un ejemplo de cómo se vería el `HashChainStatus` por
 *      fila — útil como preview visual para el revisor y como
 *      smoke test del componente compartido.
 *
 * El testid `empresa-bitacora-placeholder` se mantiene estable
 * entre este PR y Fase 20: lo que va a cambiar es el contenido del
 * bloque, no el testid. Pineado por `EmpresaPage.test.tsx` T4.
 */
import { useTranslation } from 'react-i18next';
import { Construction } from 'lucide-react';

import { HashChainStatus } from '@/components/HashChainStatus';

export function EmpresaBitacoraTab(): JSX.Element {
  const { t } = useTranslation();

  return (
    <section
      aria-label="Bitácora de cambios"
      className="space-y-4"
      data-testid="empresa-bitacora-placeholder"
    >
      <div
        role="status"
        className="flex items-start gap-3 rounded-md border border-dashed bg-muted/40 px-3 py-3 text-sm"
      >
        <Construction className="text-muted-foreground mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-medium">
            {t('empresa.bitacora.pendingTitle', 'Integración pendiente con la API de bitácora')}
          </p>
          <p className="text-muted-foreground mt-1 text-xs">
            {t(
              'empresa.bitacora.pendingBody',
              'El endpoint /api/v1/admin/audit/log requiere uuid_sucursal y Empresa es un singleton tenant-global. La consulta por uuid_referencia + tabla_afectada se cablea en Fase 20.',
            )}
          </p>
        </div>
      </div>

      <div
        className="overflow-x-auto rounded-lg border bg-card"
        data-testid="empresa-bitacora-sample"
      >
        <table className="w-full text-sm">
          <caption className="sr-only">
            {t('empresa.bitacora.sampleCaption', 'Ejemplo visual del badge HashChainStatus')}
          </caption>
          <thead>
            <tr className="border-b text-left">
              <th scope="col" className="px-3 py-2">
                {t('empresa.bitacora.col.estado', 'Estado')}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b">
              <td className="px-3 py-2">
                <HashChainStatus
                  hashAnterior="3a1f0b2c3a1f0b2c3a1f0b2c3a1f0b2c"
                  hashActual="7e9c4d1a7e9c4d1a7e9c4d1a7e9c4d1a"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
