import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

import { ClienteIdentificacionFields } from './ClienteIdentificacionFields';

describe('<ClienteIdentificacionFields /> errores', () => {
  it('muestra mensajes en español, no los códigos crudos de validación', () => {
    render(
      <ClienteIdentificacionFields
        testIdPrefix="t"
        value={{
          tipo_persona: 'empresa',
          tipo_identificador: 'NIT',
          numero_identificacion: '900123456',
          dv: '1',
          nombre: '',
          apellido: '',
          email: '',
        } as never}
        onChange={() => undefined}
        errors={{ dv: 'dv_invalido', nombre: 'nombre_requerido' }}
      />,
    );
    expect(screen.getByTestId('t-dv-error').textContent).not.toMatch(/dv_invalido/);
    expect(screen.getByTestId('t-dv-error').textContent).toMatch(/dígito de verificación/i);
    expect(screen.getByTestId('t-nombre-error').textContent).not.toMatch(/_requerido/);
  });
});
