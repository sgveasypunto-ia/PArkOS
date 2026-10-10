/**
 * `PageHeader.test.tsx` — render del header estándar de página de
 * `web_admin` (HU-homologar-page-header).
 *
 * Cubre:
 *   - T1: solo `title` → h1 presente, sin subtítulo, sin actions.
 *   - T2: `title` + `subtitle` → ambos visibles, subtítulo con la clase
 *         `text-muted-foreground`.
 *   - T3: `actions` → cluster derecho presente y contiene los children.
 *   - T4: subtítulo vacío ('') se trata como ausente (no renderiza el
 *         <p> para no dejar hueco de 1.5rem entre el H1 y la siguiente
 *         sección).
 *   - T5: data-testids estables (`page-header`, `page-header-title`,
 *         `page-header-subtitle`, `page-header-actions`) — son el
 *         contrato con los tests existentes que pineaban estos slots.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PageHeader } from './PageHeader';

describe('PageHeader', () => {
  it('renders the title only (no subtitle, no actions)', () => {
    render(<PageHeader title="Bitácora" />);

    expect(screen.getByTestId('page-header')).toBeInTheDocument();
    const title = screen.getByTestId('page-header-title');
    expect(title).toHaveTextContent('Bitácora');
    expect(title.tagName).toBe('H1');
    // Bake del peso/tamaño/tracking canónico.
    expect(title.className).toContain('text-2xl');
    expect(title.className).toContain('font-bold');
    expect(title.className).toContain('tracking-tight');

    expect(screen.queryByTestId('page-header-subtitle')).toBeNull();
    expect(screen.queryByTestId('page-header-actions')).toBeNull();
  });

  it('renders title + subtitle with muted-foreground styling', () => {
    render(
      <PageHeader
        title="Alertas"
        subtitle="Bandeja cross-branch de alertas con severidad y estado."
      />,
    );

    const subtitle = screen.getByTestId('page-header-subtitle');
    // Subtitle is a <div> (not a <p>) so it can host ReactNode
    // fragments when a page needs more than a plain string (e.g.
    // Pairing's browser-scope caption lives under subtitle).
    expect(subtitle.tagName).toBe('DIV');
    expect(subtitle).toHaveTextContent(
      'Bandeja cross-branch de alertas con severidad y estado.',
    );
    expect(subtitle.className).toContain('text-muted-foreground');
  });

  it('renders the actions cluster on the right with the given children', () => {
    render(
      <PageHeader
        title="Usuarios"
        subtitle="Crea, lista y asigna sucursales a usuarios."
        actions={<button type="button">+ Nuevo usuario</button>}
      />,
    );

    const actions = screen.getByTestId('page-header-actions');
    expect(actions).toBeInTheDocument();
    expect(actions).toHaveTextContent('+ Nuevo usuario');
  });

  it('treats an empty subtitle as absent (no <p> rendered, no gap)', () => {
    render(<PageHeader title="Empresa" subtitle="" />);

    expect(screen.queryByTestId('page-header-subtitle')).toBeNull();
  });

  it('applies the className override on the outer <header>', () => {
    render(<PageHeader title="Catálogos" className="custom-class" />);

    const header = screen.getByTestId('page-header');
    expect(header.className).toContain('custom-class');
  });
});
