import { describe, it, expect } from 'vitest';

import { buildClienteFePayload } from './clienteFePayload';
import type { PagoFormValues } from '../components/PagoModal';

function makeValues(overrides: Partial<PagoFormValues>): PagoFormValues {
  return {
    medio_pago: 'efectivo',
    monto_recibido_cop: 41000,
    voucher: '',
    fe: false,
    tipo_persona: 'empresa',
    tipo_identificador: 'NIT',
    nit: '',
    dv: '',
    nombre_cliente: '',
    apellido: '',
    email_cliente: '',
    ...overrides,
  } as PagoFormValues;
}

describe('buildClienteFePayload — cliente genérico (fe=false)', () => {
  it('returns {} regardless of leftover field values — no fe_con_datos/fe_datos_cliente leak', () => {
    const values = makeValues({
      fe: false,
      nit: '900123456',
      nombre_cliente: 'Alguien',
    });
    expect(buildClienteFePayload(values)).toEqual({});
  });
});

describe('buildClienteFePayload — empresa (NIT)', () => {
  it('builds fe_datos_cliente with tipo_identificador NIT + dv, apellido null', () => {
    const values = makeValues({
      fe: true,
      tipo_persona: 'empresa',
      tipo_identificador: 'NIT',
      nit: '900123456',
      dv: '3',
      nombre_cliente: 'Comercializadora SAS',
      email_cliente: 'facturas@comercializadora.co',
    });
    expect(buildClienteFePayload(values)).toEqual({
      fe_con_datos: true,
      fe_datos_cliente: {
        tipo_identificador: 'NIT',
        numero_identificacion: '900123456',
        dv: '3',
        nombre: 'Comercializadora SAS',
        apellido: null,
        email: 'facturas@comercializadora.co',
        telefono: null,
      },
    });
  });
});

describe('buildClienteFePayload — persona natural (CC)', () => {
  it('builds fe_datos_cliente with tipo_identificador CC, dv null, apellido set', () => {
    const values = makeValues({
      fe: true,
      tipo_persona: 'persona',
      tipo_identificador: 'CC',
      nit: '1020304050',
      dv: '9', // must be ignored — CC has no dígito de verificación
      nombre_cliente: 'Juan',
      apellido: 'Pérez',
    });
    expect(buildClienteFePayload(values)).toEqual({
      fe_con_datos: true,
      fe_datos_cliente: {
        tipo_identificador: 'CC',
        numero_identificacion: '1020304050',
        dv: null,
        nombre: 'Juan',
        apellido: 'Pérez',
        email: null,
        telefono: null,
      },
    });
  });
});
