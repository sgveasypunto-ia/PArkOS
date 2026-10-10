/**
 * `<BaseCajaEditor />` — inline editor for the base de caja of a branch.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { BaseCajaEditor, formatBase } from './BaseCajaEditor';

const ID = 'base-x';

function setup(overrides: Partial<Parameters<typeof BaseCajaEditor>[0]> = {}) {
  const onGuardar = vi.fn().mockResolvedValue(undefined);
  render(
    <BaseCajaEditor testId={ID} base="50000.0000" origen="propia" onGuardar={onGuardar} {...overrides} />,
  );
  return { onGuardar, user: userEvent.setup() };
}

describe('formatBase', () => {
  it('formats whole pesos and shows a dash when nothing is configured', () => {
    expect(formatBase('50000.0000')).toContain('50.000');
    expect(formatBase(null)).toBe('—');
  });
});

describe('<BaseCajaEditor />', () => {
  it('muestra la base y de dónde viene (propia / por defecto / sin configurar)', () => {
    setup();
    expect(screen.getByTestId(`${ID}-valor`).textContent).toContain('50.000');
    expect(screen.getByTestId(`${ID}-origen`).textContent).toBe('propia');
  });

  it('una sucursal que hereda el default lo indica', () => {
    setup({ origen: 'global' });
    expect(screen.getByTestId(`${ID}-origen`).textContent).toBe('por defecto');
  });

  it('sin base ofrece "Configurar" en vez de "Cambiar"', () => {
    setup({ base: null, origen: 'sin_configurar' });
    expect(screen.getByTestId(`${ID}-cambiar`).textContent).toBe('Configurar');
    expect(screen.getByTestId(`${ID}-origen`).textContent).toBe('sin configurar');
  });

  it('guarda el valor nuevo en pesos enteros y vuelve a la vista', async () => {
    const { onGuardar, user } = setup();

    await user.click(screen.getByTestId(`${ID}-cambiar`));
    const input = screen.getByTestId(`${ID}-input`) as HTMLInputElement;
    expect(input.value).toBe('50000');
    await user.clear(input);
    await user.type(input, '120000');
    await user.click(screen.getByTestId(`${ID}-guardar`));

    await waitFor(() => expect(onGuardar).toHaveBeenCalledWith(120000));
    expect(await screen.findByTestId(`${ID}-vista`)).not.toBeNull();
  });

  it('rechaza valores vacíos, negativos o con decimales sin llamar al servidor', async () => {
    const { onGuardar, user } = setup();

    await user.click(screen.getByTestId(`${ID}-cambiar`));
    const input = screen.getByTestId(`${ID}-input`);
    for (const invalido of ['', '-5', '10.5']) {
      await user.clear(input);
      if (invalido !== '') await user.type(input, invalido);
      await user.click(screen.getByTestId(`${ID}-guardar`));
      expect(screen.getByTestId(`${ID}-error`)).not.toBeNull();
    }
    expect(onGuardar).not.toHaveBeenCalled();
  });

  it('si el servidor falla muestra el error y deja editar', async () => {
    const onGuardar = vi.fn().mockRejectedValue(new Error('403 sin permiso'));
    const user = userEvent.setup();
    render(<BaseCajaEditor testId={ID} base={null} origen="sin_configurar" onGuardar={onGuardar} />);

    await user.click(screen.getByTestId(`${ID}-cambiar`));
    await user.type(screen.getByTestId(`${ID}-input`), '90000');
    await user.click(screen.getByTestId(`${ID}-guardar`));

    expect((await screen.findByTestId(`${ID}-error`)).textContent).toContain('403 sin permiso');
    expect(screen.getByTestId(`${ID}-input`)).not.toBeNull();
  });
});
