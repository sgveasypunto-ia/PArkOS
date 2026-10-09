/**
 * `<BaseCajaAviso />` — dashboard notice right after a shift opens.
 *
 * The operator is never asked for a value: the base de caja is a branch
 * parameter configured by administration. This tells them which base they
 * received (the one the server recorded in the session) and who to ask if in
 * doubt. Dismissible; the same text lives permanently in the status-bar
 * dropdown (`TurnoActivoToggle`).
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';

import type { SesionRead } from '../api/sesionActivaApi';
import { baseAvisoPendiente, limpiarBaseAviso } from '../lib/baseCajaAviso';
import { formatCOP } from '../lib/format';

export interface BaseCajaAvisoProps {
  sesion: SesionRead | null;
}

export function BaseCajaAviso({ sesion }: BaseCajaAvisoProps): JSX.Element | null {
  const { t } = useTranslation(['caja']);
  const [descartado, setDescartado] = useState(false);

  if (sesion === null || descartado || !baseAvisoPendiente(sesion.uuid)) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="base-caja-aviso"
      className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-card px-3 py-2 text-sm"
    >
      <span>
        <strong data-testid="base-caja-aviso-texto">
          {t('caja:baseCajaAviso.titulo', {
            defaultValue: 'Turno abierto. La base de caja de esta sucursal es {{base}}.',
            base: formatCOP(sesion.valor_inicial_efectivo),
          })}
        </strong>{' '}
        <span className="text-muted-foreground" data-testid="base-caja-aviso-dudas">
          {t('caja:baseCajaAviso.dudas', {
            defaultValue:
              'Este valor lo define la administración. Si tienes dudas, consulta con el supervisor o el administrador del sistema.',
          })}
        </span>
      </span>
      <Button
        type="button"
        size="sm"
        variant="outline"
        data-testid="base-caja-aviso-cerrar"
        onClick={() => {
          limpiarBaseAviso();
          setDescartado(true);
        }}
      >
        {t('caja:baseCajaAviso.entendido', { defaultValue: 'Entendido' })}
      </Button>
    </div>
  );
}
