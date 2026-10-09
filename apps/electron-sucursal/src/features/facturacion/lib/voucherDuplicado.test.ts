import { describe, it, expect } from 'vitest';
import { leerVoucherDuplicado } from './voucherDuplicado';

const httpError = (status: number, body: unknown) =>
  Object.assign(new Error('http'), { status, body: JSON.stringify(body) });

describe('leerVoucherDuplicado', () => {
  it('reconoce el 422 voucher_datafono_duplicado y devuelve el mensaje del backend', () => {
    const err = httpError(422, {
      detail: {
        error: 'voucher_datafono_duplicado',
        message: 'El voucher TEST999 ya fue registrado hoy en esta sucursal.',
        referencia: 'TEST999',
      },
    });
    expect(leerVoucherDuplicado(err)).toEqual({
      message: 'El voucher TEST999 ya fue registrado hoy en esta sucursal.',
      referencia: 'TEST999',
    });
  });

  it('usa un mensaje por defecto si el backend no envia message', () => {
    const err = httpError(422, { detail: { error: 'voucher_datafono_duplicado' } });
    expect(leerVoucherDuplicado(err)?.message).toMatch(/voucher/i);
  });

  it('ignora otros errores', () => {
    expect(leerVoucherDuplicado(httpError(422, { detail: { error: 'otro' } }))).toBeNull();
    expect(
      leerVoucherDuplicado(httpError(500, { detail: { error: 'voucher_datafono_duplicado' } })),
    ).toBeNull();
    expect(leerVoucherDuplicado(new Error('x'))).toBeNull();
    expect(leerVoucherDuplicado(null)).toBeNull();
    expect(leerVoucherDuplicado({ status: 422, body: 'no-json' })).toBeNull();
  });
});
