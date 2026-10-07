import { describe, expect, it } from 'vitest';

import { feEstadoLabel, feWarningMessage } from './feEstado';

const t = (_key: string, opts?: Record<string, unknown>): string => String(opts?.defaultValue ?? _key);

describe('feWarningMessage (always-on electronic invoice)', () => {
  it('is null when the FE went out (no code, not pending)', () => {
    expect(feWarningMessage(null, false, t)).toBeNull();
    expect(feWarningMessage(undefined, undefined, t)).toBeNull();
  });

  it('says it is pending and retried automatically', () => {
    const msg = feWarningMessage(null, true, t) ?? '';
    expect(msg).toMatch(/pendiente, se reintenta sola/i);
  });

  it.each([
    ['resolucion_facturacion_no_encontrada', /resolución de facturación/],
    ['numeracion_agotada', /numeración/],
    ['resolucion_sin_prefijo', /prefijo/],
    ['missing_sucursal_context', /sucursal/],
    ['fe_error_inesperado', /inesperado/],
  ])('%s -> keeps the generic notice and appends the reason', (code, rx) => {
    const msg = feWarningMessage(code, true, t) ?? '';
    expect(msg).toMatch(/se reintenta sola/);
    expect(msg).toMatch(rx);
  });

  it('an unknown code still produces the generic notice', () => {
    expect(feWarningMessage('algo_nuevo', true, t)).toMatch(/se reintenta sola/);
  });
});

describe('feEstadoLabel', () => {
  it('labels every DIAN state', () => {
    expect(feEstadoLabel('pendiente', t)).toMatch(/pendiente/i);
    expect(feEstadoLabel('enviado', t)).toMatch(/Enviada/);
    expect(feEstadoLabel('aceptado', t)).toMatch(/Aceptada/);
    expect(feEstadoLabel('rechazado', t)).toMatch(/Rechazada/);
  });
});
