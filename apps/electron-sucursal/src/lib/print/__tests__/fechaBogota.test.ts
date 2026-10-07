/**
 * FB2 — the backend stores NAIVE UTC timestamps; the printed slips must show
 * Bogotá wall-clock time regardless of the machine zone (the reprint printed
 * the raw UTC hour, 21:07 instead of 16:07).
 */
import { describe, it, expect } from 'vitest';

import { formatFecha, formatFechaCorta, formatHora } from '../escposTemplates';
import { build } from '../escposBuilder';
import { renderEntradaTiqueteHtml } from '../fallbackBrowser';
import { buildReimpresionEntradaPayload } from '../printBuilder';
import type { Ingreso } from '../../../features/operacion/api/ingresoActivoApi';

function ingreso(fecha: string): Ingreso {
  return {
    uuid: '00000000-0000-4000-8000-000000000001',
    uuid_sucursal: '00000000-0000-4000-8000-000000000002',
    placa: 'ABC123',
    fecha_ingreso: fecha,
    uuid_subscripcion_cliente: null,
    consecutivo: null,
    uuid_tipo_vehiculo: null,
  };
}

describe('formatHora / formatFecha — naive UTC to Bogotá', () => {
  it('a naive timestamp is read as UTC (21:07 UTC → 16:07)', () => {
    expect(formatHora('2026-10-07T21:07:00')).toBe('16:07');
  });
  it('a Z timestamp gives the same Bogotá hour', () => {
    expect(formatHora('2026-10-07T21:07:00Z')).toBe('16:07');
    expect(formatHora('2026-10-07T21:07:00.123456')).toBe('16:07');
  });
  it('an explicit offset is honoured', () => {
    expect(formatHora('2026-10-07T16:07:00-05:00')).toBe('16:07');
  });
  it('the date rolls back across midnight UTC', () => {
    expect(formatFecha('2026-10-08T03:30:00')).toBe('07/10/2026');
    expect(formatFechaCorta('2026-10-08T03:30:00')).toBe('07/10/2026 22:30');
  });
});

describe('reprint ticket prints the Bogotá hour of the stored naive UTC instant', () => {
  const payload = buildReimpresionEntradaPayload(ingreso('2026-10-07T21:07:00'), 'Tiquete perdido');

  it('keeps the original instant (read as UTC) in fechaEntrada', () => {
    expect(payload.payload.fechaEntrada).toBe('2026-10-07T21:07:00.000Z');
  });
  it('ESC/POS says Hora: 16:07', () => {
    expect(build('reimpresion', payload).toString('utf8')).toContain('Hora: 16:07');
  });
  it('HTML says Hora: 16:07', () => {
    expect(renderEntradaTiqueteHtml(payload.payload)).toContain('<p>Hora: 16:07</p>');
  });
});
