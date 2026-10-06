import { describe, expect, it } from 'vitest';

import { abrirTurnoSchema, cerrarTurnoSchema, OBSERVACIONES_CIERRE_MAX } from './turnoSchema';

const UUID_A = '6730a59a-96b3-4950-bd23-95c5f3325fed';
const UUID_B = '11111111-2222-4333-8444-555555555555';

describe('abrirTurnoSchema', () => {
  it('accepts the form values WITHOUT valor_inicial_datafono (field no longer rendered)', () => {
    const result = abrirTurnoSchema.safeParse({
      uuid_sucursal: UUID_A,
      uuid_usuario: UUID_B,
      valor_inicial_efectivo: '50000',
      observaciones: '',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.valor_inicial_efectivo).toBe(50000);
    }
  });

  it('still rejects a missing valor_inicial_efectivo', () => {
    const result = abrirTurnoSchema.safeParse({
      uuid_sucursal: UUID_A,
      uuid_usuario: UUID_B,
    });
    expect(result.success).toBe(false);
  });
});

describe('cerrarTurnoSchema', () => {
  it('accepts a close WITHOUT datafono or justificacion (PT-4 / PT-6)', () => {
    const result = cerrarTurnoSchema.safeParse({ valor_efectivo_reportado: 120000 });
    expect(result.success).toBe(true);
  });

  it('strips legacy datafono/justificacion keys instead of requiring them', () => {
    const result = cerrarTurnoSchema.safeParse({
      valor_efectivo_reportado: 10,
      valor_datafono_reportado: 5,
      justificacion: 'x',
    });
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data).toEqual({ valor_efectivo_reportado: 10 });
    }
  });

  it('caps observaciones_cierre at the backend limit', () => {
    const ok = cerrarTurnoSchema.safeParse({
      valor_efectivo_reportado: 0,
      observaciones_cierre: 'a'.repeat(OBSERVACIONES_CIERRE_MAX),
    });
    const tooLong = cerrarTurnoSchema.safeParse({
      valor_efectivo_reportado: 0,
      observaciones_cierre: 'a'.repeat(OBSERVACIONES_CIERRE_MAX + 1),
    });
    expect(ok.success).toBe(true);
    expect(tooLong.success).toBe(false);
  });
});
