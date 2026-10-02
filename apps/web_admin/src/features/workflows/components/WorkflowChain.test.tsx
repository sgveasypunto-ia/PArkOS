/**
 * `WorkflowChain.test.tsx` -- generic timeline contract. Deliberately
 * uses a FAKE "ticket" status vocabulary (not `alerta`) to prove the
 * component is domain-agnostic, per its own docblock.
 *
 *  - T1: renders one item per transition, in the order given.
 *  - T2: the `renderStatusBadge` injection renders instead of the raw
 *    `status` string when provided.
 *  - T3: without `renderStatusBadge`, the raw `status` string renders.
 *  - T4: `observaciones: null` does not render a stray note paragraph.
 *  - T5: empty / loading / error states each render their own testid.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WorkflowChain, type WorkflowTransition } from './WorkflowChain';

const TRANSITIONS: WorkflowTransition[] = [
  { id: 't1', status: 'creado', timestamp: '2026-09-01T08:00:00', actor: 'uuid-a', observaciones: null },
  { id: 't2', status: 'cerrado', timestamp: '2026-09-02T08:00:00', actor: 'uuid-b', observaciones: 'Cerrado por el admin.' },
];

describe('WorkflowChain', () => {
  it('T1: renders one item per transition in order', () => {
    render(<WorkflowChain transitions={TRANSITIONS} />);
    const list = screen.getByTestId('workflow-chain');
    const items = list.querySelectorAll('li');
    expect(items).toHaveLength(2);
    expect(screen.getByTestId('workflow-chain-item-t1')).toBeInTheDocument();
    expect(screen.getByTestId('workflow-chain-item-t2')).toBeInTheDocument();
  });

  it('T2: renderStatusBadge renders instead of the raw status string', () => {
    render(
      <WorkflowChain
        transitions={TRANSITIONS}
        renderStatusBadge={(status) => <span data-testid={`fake-badge-${status}`}>{status.toUpperCase()}</span>}
      />,
    );
    expect(screen.getByTestId('fake-badge-creado')).toHaveTextContent('CREADO');
  });

  it('T3: without renderStatusBadge, the raw status string renders', () => {
    render(<WorkflowChain transitions={TRANSITIONS} />);
    expect(screen.getByTestId('workflow-chain-item-t1')).toHaveTextContent('creado');
  });

  it('T4: observaciones: null renders no stray note', () => {
    render(<WorkflowChain transitions={[TRANSITIONS[0]!]} />);
    const item = screen.getByTestId('workflow-chain-item-t1');
    expect(item.querySelectorAll('p')).toHaveLength(1); // only the "Actor: ..." line
  });

  it('T5: loading / error / empty each render their own state', () => {
    const { rerender } = render(<WorkflowChain transitions={[]} isLoading />);
    expect(screen.getByTestId('workflow-chain-loading')).toBeInTheDocument();

    rerender(<WorkflowChain transitions={[]} error={new Error('boom')} />);
    expect(screen.getByTestId('workflow-chain-error')).toBeInTheDocument();

    rerender(<WorkflowChain transitions={[]} />);
    expect(screen.getByTestId('workflow-chain-empty')).toBeInTheDocument();
  });
});
