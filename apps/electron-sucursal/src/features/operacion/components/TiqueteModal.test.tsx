/**
 * Unit tests for `TiqueteModal` (HU-F6.1, T7).
 *
 * Spec scenarios:
 *   - 201 → modal opens with role="dialog" (axe-core target).
 *   - Imprimir button → `bridge.imprimir({ buffer, ticketId })` fired once.
 *   - Siguiente button → resets form / clears cache.
 *
 * Mock `window.bridge.imprimir` because the dialog calls it directly.
 * Uses `fireEvent` (from `@testing-library/react`).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { TiqueteModal } from './TiqueteModal';

const imprimirMock = vi.fn();

beforeEach(() => {
  imprimirMock.mockReset();
  imprimirMock.mockResolvedValue({ ok: true });
  (globalThis as unknown as { window: unknown }).window = {
    bridge: { imprimir: imprimirMock },
  };
});

describe('TiqueteModal', () => {
  it('renders with role="dialog" when open', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        buildPrintPayload={() => ({
          buffer: Buffer.from('hello').toString('base64'),
          ticketId: 'ticket-1',
        })}
        onSiguiente={vi.fn()}
      />,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows the Mensualidad label when tipo_entrada=MENSUALIDAD', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="MENSUALIDAD"
        buildPrintPayload={() => ({
          buffer: Buffer.from('hello').toString('base64'),
          ticketId: 'ticket-1',
        })}
        onSiguiente={vi.fn()}
      />,
    );
    expect(screen.getByText(/mensualidad/i)).toBeInTheDocument();
  });

  it('calls bridge.imprimir with the payload from buildPrintPayload on Imprimir click', async () => {
    const buildPrintPayload = vi.fn((uuid_ingreso: string) => ({
      buffer: Buffer.from(`entrada:${uuid_ingreso}`).toString('base64'),
      ticketId: uuid_ingreso,
    }));
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        buildPrintPayload={buildPrintPayload}
        onSiguiente={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /imprimir/i }));
    await waitFor(() => expect(imprimirMock).toHaveBeenCalledTimes(1));
    expect(buildPrintPayload).toHaveBeenCalledWith(
      '11111111-1111-1111-1111-111111111111',
    );
    expect(imprimirMock).toHaveBeenCalledWith({
      buffer: Buffer.from(
        'entrada:11111111-1111-1111-1111-111111111111',
      ).toString('base64'),
      ticketId: '11111111-1111-1111-1111-111111111111',
    });
  });

  it('calls onSiguiente when the Siguiente button is clicked', () => {
    const onSiguiente = vi.fn();
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
        })}
        onSiguiente={onSiguiente}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /siguiente/i }));
    expect(onSiguiente).toHaveBeenCalledTimes(1);
  });

  it('shows an inline error when bridge.imprimir returns ok:false', async () => {
    imprimirMock.mockResolvedValueOnce({ ok: false });
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
        })}
        onSiguiente={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /imprimir/i }));
    await waitFor(() =>
      expect(
        screen.getByRole('alert'),
      ).toHaveTextContent(/no se pudo imprimir/i),
    );
  });
});
