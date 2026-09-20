/**
 * Tests for `calcularMontoProporcional` pure helper (HU-F9.1, REQ-OPS-178).
 *
 * Coverage (4 unit tests):
 *   T1: fecha.day <= 15 → returns null (no prorrateo applied per A-09).
 *   T2: fecha.day > 15 → returns (valor / duracion_dias) * dias_restantes_mes.
 *   T3: plan.valor=30000, duracion_dias=30, fecha=2026-09-19 (day 19) → 11000.
 *   T4: fecha=2026-09-30 (last day of month) → dias_restantes_mes=1 → 1000.
 */
import { describe, it, expect } from 'vitest';

import {
  calcularMontoProporcional,
  PlanDuracionDiasInvalidoError,
} from './prorrateo';

describe('calcularMontoProporcional — REQ-OPS-178 (A-09 mirror)', () => {
  it('T1: fecha.day <= 15 → returns null (no prorrateo applied per A-09)', () => {
    const result = calcularMontoProporcional(
      { valor: 30000, duracion_dias: 30 },
      new Date(2026, 8, 10),
    );
    expect(result).toBeNull();
  });

  it('T2: fecha.day > 15 → returns (valor / duracion_dias) * dias_restantes_mes', () => {
    // 2026-09-20 (day 20): dias_restantes = 30 - 20 = 10; valor_dia = 30000/30 = 1000.
    const result = calcularMontoProporcional(
      { valor: 30000, duracion_dias: 30 },
      new Date(2026, 8, 20),
    );
    expect(result).toBe(10000);
  });

  it('T3: plan.valor=30000, duracion_dias=30, fecha=2026-09-19 (day 19) → 11000', () => {
    // 2026-09-19 (day 19): dias_restantes = 30 - 19 = 11; valor_dia = 1000; mp = 11000.
    const result = calcularMontoProporcional(
      { valor: 30000, duracion_dias: 30 },
      new Date(2026, 8, 19),
    );
    expect(result).toBe(11000);
  });

  it('T4: fecha=2026-09-30 (last day of month) → dias_restantes_mes=1 → 1000', () => {
    const result = calcularMontoProporcional(
      { valor: 30000, duracion_dias: 30 },
      new Date(2026, 8, 30),
    );
    expect(result).toBe(1000);
  });

  it('T5: duracion_dias <= 0 → throws PlanDuracionDiasInvalidoError', () => {
    expect(() =>
      calcularMontoProporcional(
        { valor: 30000, duracion_dias: 0 },
        new Date(2026, 8, 20),
      ),
    ).toThrow(PlanDuracionDiasInvalidoError);
  });
});
