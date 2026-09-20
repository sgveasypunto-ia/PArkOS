/**
 * Tests for `<SalidaSheet />` (REQ-OPS-138 single-drawer invariant
 * + F7.1 dashboard wiring).
 *
 * Coverage:
 *   SS1: closed by default — renders nothing when `openDrawer !== 'salida'`.
 *   SS2: open via store → mounts <SalidaPanel /> inside <Sheet>.
 *   SS3: Sheet onOpenChange(false) → close() invoked → store clears
 *        openDrawer + initialPlaca.
 *   SS4: open with placa → <SalidaPanel /> receives that placa as
 *        the `initialPlaca` prop so it can pre-fill the form.
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

// Capture the initialPlaca prop the sheet threads into SalidaPanel.
const mockSalidaPanel = vi.fn();
vi.mock('./SalidaPanel', () => ({
  SalidaPanel: (props: {
    uuid_ingreso: string | null;
    initialPlaca?: string | null;
  }) => {
    mockSalidaPanel(props);
    return <div data-testid="salida-panel-stub" />;
  },
}));

import {
  useDashboardDrawerStore,
} from '@/store/dashboardDrawerStore';
import { SalidaSheet } from './SalidaSheet';

beforeEach(() => {
  mockSalidaPanel.mockClear();
  useDashboardDrawerStore.getState().close();
  cleanup();
});

describe('<SalidaSheet /> — REQ-OPS-138 + F7.1 wiring', () => {
  it('SS1: closed by default — renders nothing when openDrawer is null', () => {
    const { container } = render(<SalidaSheet />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('salida-sheet')).toBeNull();
    expect(mockSalidaPanel).not.toHaveBeenCalled();
  });

  it('SS1b: closed when openDrawer is some other kind (e.g. ingreso)', () => {
    useDashboardDrawerStore.getState().open('ingreso', 'anchor-x');
    const { container } = render(<SalidaSheet />);
    expect(container.firstChild).toBeNull();
    expect(mockSalidaPanel).not.toHaveBeenCalled();
    // Restore for the next test.
    useDashboardDrawerStore.getState().close();
  });

  it('SS2: open via store → mounts SalidaPanel with uuid_ingreso=null and initialPlaca', () => {
    useDashboardDrawerStore.getState().open('salida', 'placa-hero-input', 'ABC123');
    render(<SalidaSheet />);
    expect(mockSalidaPanel).toHaveBeenCalled();
    expect(mockSalidaPanel.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        uuid_ingreso: null,
        initialPlaca: 'ABC123',
      }),
    );
  });

  it('SS3: Sheet onOpenChange(false) → close() → store clears openDrawer', () => {
    useDashboardDrawerStore.getState().open('salida', 'placa-hero-input', 'ABC123');
    expect(useDashboardDrawerStore.getState().openDrawer).toBe('salida');
    useDashboardDrawerStore.getState().close();
    expect(useDashboardDrawerStore.getState().openDrawer).toBeNull();
    expect(useDashboardDrawerStore.getState().initialPlaca).toBeNull();
  });

  it('SS4: open with placa → SalidaPanel receives that placa as initialPlaca', () => {
    useDashboardDrawerStore
      .getState()
      .open('salida', 'placa-hero-input', 'ABC12D');
    render(<SalidaSheet />);
    expect(mockSalidaPanel).toHaveBeenCalledWith(
      expect.objectContaining({ initialPlaca: 'ABC12D' }),
    );
  });

  it('SS5: open without placa → SalidaPanel receives initialPlaca=null', () => {
    useDashboardDrawerStore.getState().open('salida', 'hotkey-chip');
    render(<SalidaSheet />);
    expect(mockSalidaPanel).toHaveBeenCalledWith(
      expect.objectContaining({ initialPlaca: null }),
    );
  });
});
