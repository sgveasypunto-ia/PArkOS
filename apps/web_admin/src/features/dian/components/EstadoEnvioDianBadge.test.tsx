import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { EstadoEnvioDianBadge } from './EstadoEnvioDianBadge';

describe('EstadoEnvioDianBadge', () => {
  it("shows the in-flight 'activo' row as En proceso instead of a dash", () => {
    render(<EstadoEnvioDianBadge estado="activo" />);
    expect(screen.getByTestId('estado-envio-dian-badge-en_proceso')).toHaveTextContent('En proceso');
    expect(screen.queryByTestId('estado-envio-dian-badge-none')).toBeNull();
  });

  it('still shows a dash for a null or unknown estado', () => {
    const { rerender } = render(<EstadoEnvioDianBadge estado={null} />);
    expect(screen.getByTestId('estado-envio-dian-badge-none')).toBeInTheDocument();
    rerender(<EstadoEnvioDianBadge estado="algo_raro" />);
    expect(screen.getByTestId('estado-envio-dian-badge-none')).toBeInTheDocument();
  });

  it('keeps showing the terminal outcomes', () => {
    render(<EstadoEnvioDianBadge estado="timeout" />);
    expect(screen.getByTestId('estado-envio-dian-badge-timeout')).toBeInTheDocument();
  });
});
