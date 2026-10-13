/**
 * `severity.test.ts` -- contrato de vocabulario de severidad.
 *
 * `prod.alert_types.severity` (critical|warning|info) es el vocabulario
 * canonico (el que consume web_admin). `GET /workflows/alert-types` responde
 * el vocabulario legado de sucursal (alta|media|baja). `severityToSeveridad`
 * es el UNICO punto de traduccion en esta app y espeja
 * `repo/alert_types.py::severity_to_severidad` del backend.
 */
import { describe, it, expect } from 'vitest';

import { ALERT_CODE_FALLBACK } from '../../../features/alertas/constants';
import { AlertTypeSchema } from '../../api/schemas/alertas';
import {
  ALERT_SEVERITIES,
  SEVERIDADES,
  severityToSeveridad,
  type AlertSeverity,
  type Severidad,
} from '../severity';

describe('severityToSeveridad -- contrato critical/warning/info -> alta/media/baja', () => {
  const tabla: Array<[AlertSeverity, Severidad]> = [
    ['critical', 'alta'],
    ['warning', 'media'],
    ['info', 'baja'],
  ];

  it.each(tabla)('%s -> %s', (severity, severidad) => {
    expect(severityToSeveridad(severity)).toBe(severidad);
  });

  it('cubre exactamente ambos vocabularios', () => {
    expect([...ALERT_SEVERITIES].sort()).toEqual(['critical', 'info', 'warning']);
    expect([...SEVERIDADES].sort()).toEqual(['alta', 'baja', 'media']);
    expect(new Set(ALERT_SEVERITIES.map(severityToSeveridad))).toEqual(new Set(SEVERIDADES));
  });

  it('el esquema del cable de alert-types acepta exactamente SEVERIDADES', () => {
    for (const severidad of SEVERIDADES) {
      expect(
        AlertTypeSchema.safeParse({ codigo: 'x', severidad, descripcion: 'd', mensaje: 'm' })
          .success,
      ).toBe(true);
    }
    expect(
      AlertTypeSchema.safeParse({ codigo: 'x', severidad: 'critical', descripcion: 'd', mensaje: 'm' })
        .success,
    ).toBe(false);
  });

  it('ALERT_CODE_FALLBACK usa solo valores producidos por el helper', () => {
    const permitidos = new Set<string>(SEVERIDADES);
    for (const [code, entry] of Object.entries(ALERT_CODE_FALLBACK)) {
      expect(permitidos.has(entry.severidad), code).toBe(true);
    }
  });
});
