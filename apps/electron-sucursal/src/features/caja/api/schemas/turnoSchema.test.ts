import { describe, expect, it } from 'vitest';

import { abrirTurnoSchema } from './turnoSchema';

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
