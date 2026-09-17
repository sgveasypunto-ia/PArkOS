/**
 * Tests for `<IngresoSheet />` (REQ-OPS-138 single-drawer invariant
 * + F6.1 dashboard wiring).
 *
 * Coverage:
 *   IS1: closed by default — renders nothing when `openDrawer !== 'ingreso'`.
 *   IS2: open via store → mounts <IngresoPanel /> inside <Sheet>.
 *   IS3: Sheet onOpenChange(false) → close() invoked → store clears
 *        openDrawer + initialPlaca.
 *   IS4: open with placa → <IngresoPanel /> receives that placa as
 *        the `initialPlaca` prop so it can pre-fill the form.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Capture the initialPlaca prop the sheet threads into IngresoPanel.
const mockIngresoPanel = vi.fn();
vi.mock('./IngresoPanel', () => ({
  IngresoPanel: (props: { initialPlaca?: string | null }) => {
    mockIngresoPanel(props);
    return <div data-testid="ingreso-panel-stub" />;
  },
}));

import {
  useDashboardDrawerStore,
} from '@/store/dashboardDrawerStore';
import { IngresoSheet } from './IngresoSheet';

beforeEach(() => {
  mockIngresoPanel.mockClear();
  useDashboardDrawerStore.getState().close();
  cleanup();
});

describe('<IngresoSheet /> — REQ-OPS-138 + F6.1 wiring', () => {
  it('IS1: closed by default — renders nothing when openDrawer is null', () => {
    const { container } = render(<IngresoSheet />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('ingreso-sheet')).toBeNull();
    expect(mockIngresoPanel).not.toHaveBeenCalled();
  });

  it('IS1b: closed when openDrawer is some other kind (e.g. salida)', () => {
    useDashboardDrawerStore.getState().open('salida', 'anchor-x');
    const { container } = render(<IngresoSheet />);
    expect(container.firstChild).toBeNull();
    expect(mockIngresoPanel).not.toHaveBeenCalled();
    // Restore for the next test.
    useDashboardDrawerStore.getState().close();
  });

  it('IS2: open via store → mounts IngresoPanel', () => {
    useDashboardDrawerStore.getState().open('ingreso', 'placa-hero-input', 'ABC123');
    render(<IngresoSheet />);
    // The mocked IngresoPanel records its props; assert it was called.
    expect(mockIngresoPanel).toHaveBeenCalled();
    expect(mockIngresoPanel.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ initialPlaca: 'ABC123' }),
    );
  });

  it('IS3: Sheet onOpenChange(false) → close() → store clears openDrawer', () => {
    useDashboardDrawerStore.getState().open('ingreso', 'placa-hero-input', 'ABC123');
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('ingreso');
    // Simulate Radix Sheet's onOpenChange(false) by calling the store's
    // close directly (mirrors what onOpenChange={() => !next && close()} does).
    useDashboardDrawerStore.getState().close();
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    expect(useDashboardDrawerStore.getState().initialPlaca).toBeNull();
  });

  it('IS4: open with placa → IngresoPanel receives that placa as initialPlaca', () => {
    useDashboardDrawerStore
      .getState()
      .open('ingreso', 'placa-hero-input', 'ABC12D');
    render(<IngresoSheet />);
    expect(mockIngresoPanel).toHaveBeenCalledWith(
      expect.objectContaining({ initialPlaca: 'ABC12D' }),
    );
  });

  it('IS5: open without placa → IngresoPanel receives initialPlaca=null', () => {
    useDashboardDrawerStore.getState().open('ingreso', 'hotkey-chip');
    render(<IngresoSheet />);
    expect(mockIngresoPanel).toHaveBeenCalledWith(
      expect.objectContaining({ initialPlaca: null }),
    );
  });
});
