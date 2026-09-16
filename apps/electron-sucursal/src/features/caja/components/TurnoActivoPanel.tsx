/**
 * `<TurnoActivoPanel />` — organism puramente presentational (F3.3 — T4, DEC-F3.3-05).
 *
 * Recibe props `{ sesion, onCerrarClick }` (REQ-OPS-121). NO consume
 * `useSesionActiva`, NO invoca `parkosFetch`, NO maneja state interno más
 * allá de props (idéntico pattern F3.1 DEC-F3.1-02 + LoginForm container/
 * presentational split).
 *
 * Renderiza `<Card>` shadcn con:
 *   - `<CardTitle>{t('caja:turnoActivo')}</CardTitle>` heading semántico `<h3>`
 *     (REQ-OPS-124 S5 axe-core WCAG 2.1 AA).
 *   - `<CardContent>` con uuid, valores iniciales vía `formatCOP`, timestamp
 *     apertura vía `formatTiempoTranscurrido`, observaciones opcional.
 *   - `<CardFooter>` con botón "Cerrar turno" (`onClick={onCerrarClick}`).
 *
 * WCAG 2.1 AA (RNF-022):
 *   - Contraste ≥4.5:1 via shadcn tokens F2.1 baseline.
 *   - Headings semánticos (CardTitle → h3).
 *   - Foco visible al tab del Button (focus-visible:ring-2).
 */
import { useTranslation } from 'react-i18next';

import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/renderer/components/ui/card';
import { Button } from '@/renderer/components/ui/button';

import type { SesionRead } from '../api/sesionActivaApi';
import { formatCOP, formatTiempoTranscurrido } from '../lib/format';

export interface TurnoActivoPanelProps {
  sesion: SesionRead;
  onCerrarClick: () => void;
}

export function TurnoActivoPanel({
  sesion,
  onCerrarClick,
}: TurnoActivoPanelProps): JSX.Element {
  const { t } = useTranslation('caja');
  return (
    <Card data-testid="turno-activo-panel">
      <CardHeader>
        <CardTitle>{t('turnoActivo')}</CardTitle>
      </CardHeader>
      <CardContent>
        <p data-testid="turno-activo-uuid">
          <strong>UUID:</strong> {sesion.uuid}
        </p>
        <p data-testid="turno-activo-valor-efectivo">
          <strong>{t('valorInicialEfectivo')}:</strong>{' '}
          {formatCOP(sesion.valor_inicial_efectivo)}
        </p>
        <p data-testid="turno-activo-valor-datafono">
          <strong>{t('valorInicialDatafono')}:</strong>{' '}
          {formatCOP(sesion.valor_inicial_datafono)}
        </p>
        <p data-testid="turno-activo-apertura">
          <strong>Apertura:</strong>{' '}
          {formatTiempoTranscurrido(sesion.timestamp_apertura)}
        </p>
        {sesion.observaciones !== null &&
          sesion.observaciones !== undefined &&
          sesion.observaciones !== '' && (
            <p data-testid="turno-activo-observaciones">
              <strong>{t('observaciones')}:</strong> {sesion.observaciones}
            </p>
          )}
      </CardContent>
      <CardFooter>
        <Button onClick={onCerrarClick} data-testid="turno-activo-cerrar">
          {t('cerrarTurno')}
        </Button>
      </CardFooter>
    </Card>
  );
}