/**
 * Zod mirror of BE `ResumenCierreTurnoRead` + key-set lock against
 * `backend/tests/integration/test_resumen_cierre_turno.py`.
 */
import { describe, expect, it } from 'vitest';

import { ResumenCierreTurnoSchema } from '../resumen-cierre-turno';

const BASE_OK = {
  uuid_sesion: '00000000-0000-0000-0000-000000000001',
  uuid_sucursal: '00000000-0000-0000-0000-000000000002',
  timestamp_calculo: '2026-10-06T18:00:00',
  ingresos_count: 7,
  salidas_count: 5,
  transacciones_count: 7,
  medios_pago: [
    { medio_pago: 'efectivo', pagos_count: 4, total_cop: '40000.0000' },
    { medio_pago: 'datafono', pagos_count: 3, total_cop: 30000 },
  ],
  reversos_count: 1,
  reversos_total_cop: '5000',
};

describe('ResumenCierreTurnoSchema', () => {
  it('parses the canonical payload and coerces Decimal strings', () => {
    const parsed = ResumenCierreTurnoSchema.parse(BASE_OK);
    expect(parsed.medios_pago[0]?.total_cop).toBe(40000);
    expect(parsed.reversos_total_cop).toBe(5000);
  });

  it('mirrors the BE key set exactly', () => {
    expect(Object.keys(ResumenCierreTurnoSchema.shape).sort()).toEqual(
      [
        'uuid_sesion',
        'uuid_sucursal',
        'timestamp_calculo',
        'ingresos_count',
        'salidas_count',
        'transacciones_count',
        'medios_pago',
        'reversos_count',
        'reversos_total_cop',
        'base_entregada',
        'efectivo_reportado',
        'producido',
      ].sort(),
    );
  });

  it('keeps the cash-handover fields null until an arqueo exists and coerces Decimal strings', () => {
    const sinArqueo = ResumenCierreTurnoSchema.parse({
      ...BASE_OK,
      base_entregada: '100000.0000',
      efectivo_reportado: null,
      producido: null,
    });
    expect(sinArqueo.base_entregada).toBe(100000);
    expect(sinArqueo.efectivo_reportado).toBeNull();
    expect(sinArqueo.producido).toBeNull();

    const conArqueo = ResumenCierreTurnoSchema.parse({
      ...BASE_OK,
      base_entregada: '100000',
      efectivo_reportado: '350000',
      producido: '250000',
    });
    expect(conArqueo.producido).toBe(250000);
  });

  it('rejects unknown keys (strict) and missing required fields', () => {
    expect(() => ResumenCierreTurnoSchema.parse({ ...BASE_OK, extra: 1 })).toThrow();
    const { uuid_sesion: _omit, ...rest } = BASE_OK;
    expect(() => ResumenCierreTurnoSchema.parse(rest)).toThrow();
  });
});
