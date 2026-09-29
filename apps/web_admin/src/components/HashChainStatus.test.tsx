/**
 * `<HashChainStatus />` — invariantes del badge de hash chain
 * (HU-F15.2 T3, `plan.md:3552`).
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { HashChainStatus } from './HashChainStatus';

describe('HashChainStatus', () => {
  it('renderiza verde cuando ambos hashes están presentes', () => {
    render(
      <HashChainStatus
        hashAnterior="abcd1234abcd1234abcd1234abcd1234"
        hashActual="ef567890ef567890ef567890ef567890"
      />,
    );
    const badge = screen.getByTestId('hash-chain-intact');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent(/abcd1234/);
    expect(badge).toHaveTextContent(/ef567890/);
  });

  it('renderiza rojo cuando falta hashAnterior', () => {
    render(<HashChainStatus hashAnterior={null} hashActual="ef567890ef567890ef567890ef567890" />);
    expect(screen.getByTestId('hash-chain-broken')).toBeInTheDocument();
  });

  it('renderiza rojo cuando falta hashActual', () => {
    render(<HashChainStatus hashAnterior="abcd1234abcd1234abcd1234abcd1234" hashActual={null} />);
    expect(screen.getByTestId('hash-chain-broken')).toBeInTheDocument();
  });

  it('renderiza rojo cuando ambos son null (fila genesis)', () => {
    render(<HashChainStatus hashAnterior={null} hashActual={null} />);
    expect(screen.getByTestId('hash-chain-broken')).toBeInTheDocument();
  });

  it('compact=true oculta los hashes abreviados', () => {
    render(
      <HashChainStatus
        hashAnterior="abcd1234abcd1234abcd1234abcd1234"
        hashActual="ef567890ef567890ef567890ef567890"
        compact
      />,
    );
    const badge = screen.getByTestId('hash-chain-intact');
    expect(badge).not.toHaveTextContent(/abcd1234/);
  });
});
