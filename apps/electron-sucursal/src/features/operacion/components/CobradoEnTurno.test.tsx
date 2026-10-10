/**
 * Contraste del rótulo en tema oscuro: `--muted-foreground` ya cumple
 * 4,5:1 sobre el popover; un modificador de opacidad (`/90`) lo baja a
 * ~3,9:1. El rótulo debe usar el token sin atenuarlo.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { CobradoEnTurno } from './CobradoEnTurno';

describe('<CobradoEnTurno /> — contraste del rótulo', () => {
  it('el rótulo usa text-muted-foreground sin modificador de opacidad', () => {
    render(
      <CobradoEnTurno
        data={{ total_cobrado_efectivo_cop: 1500 } as never}
        error={undefined}
        isLoaded
      />,
    );
    const region = screen.getByTestId('mi-turno-cobrado');
    const rotulo = region.querySelector('span');
    expect(rotulo).not.toBeNull();
    expect(rotulo?.className).toContain('text-muted-foreground');
    expect(rotulo?.className).not.toMatch(/text-muted-foreground\/\d+/);
  });
});
