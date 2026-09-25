/**
 * Unit tests for `TiqueteModal` (HU-F6.1, T7 + HU-F11.x REQ-OPS-200).
 *
 * Spec scenarios:
 *   - 201 → modal opens with role="dialog" (axe-core target).
 *   - Imprimir button → `bridge.imprimir({ buffer, ticketId })` fired once.
 *   - HU-F11.x: ``Vehículo:`` line renders the concrete tipo name
 *     (``carro`` / ``moto`` / ``bicicleta`` / ``patineta``) so the
 *     operator sees what they committed, not just the
 *     ``ROTACION`` / ``MENSUALIDAD`` discriminator.
 *
 * REGRESSION fix (2026-09-22): removed tests for the Siguiente /
 * Anular / Hacer arqueo buttons — those CTAs were dropped from the
 * dialog (only Imprimir + Ir a salida remain). The Siguiente reset
 * path is auto-fired by Imprimir (FEATURE F), so no manual button.
 *
 * Mock `window.bridge.imprimir` because the dialog calls it directly.
 * Uses `fireEvent` (from `@testing-library/react`).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/i18n';

import { TiqueteModal } from './TiqueteModal';

const imprimirMock = vi.fn();

// NOTE: `window` here is the real jsdom global — replacing it wholesale
// (as this file used to do) strips `HTMLIFrameElement`, `MessageChannel`,
// etc. and corrupts React's scheduler for every test that renders after
// this one in the same worker. Only patch `window.bridge` and restore
// the prior value in `afterEach` (mirrors `SalidaMensualidad.test.tsx`).
let originalBridge: unknown;

beforeEach(() => {
  imprimirMock.mockReset();
  imprimirMock.mockResolvedValue({ ok: true });
  const w = globalThis as unknown as { window: { bridge?: unknown } };
  originalBridge = w.window.bridge;
  w.window.bridge = { imprimir: imprimirMock };
});

afterEach(() => {
  (globalThis as unknown as { window: { bridge?: unknown } }).window.bridge = originalBridge;
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
          cut: true,
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
          cut: true,
        })}
        onSiguiente={vi.fn()}
      />,
    );
    // REGRESSION fix (2026-09-22) added a print-preview thumbnail that
    // repeats the "Tipo:" line already shown in the summary below it,
    // so "Mensualidad" now legitimately appears twice in the dialog.
    expect(screen.getAllByText(/mensualidad/i).length).toBeGreaterThan(0);
  });

  it('HU-F11.x: shows the concrete vehicle type name when tipo_vehiculo_nombre is provided', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        tipo_vehiculo_nombre="moto"
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
          cut: true,
        })}
        onSiguiente={vi.fn()}
      />,
    );
    // The Vehículo: line is rendered with the concrete name.
    expect(screen.getByText(/Veh[íi]culo/i)).toBeInTheDocument();
    expect(screen.getByText(/moto/)).toBeInTheDocument();
  });

  it('HU-F11.x: hides the vehicle line when tipo_vehiculo_nombre is null', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        tipo_vehiculo_nombre={null}
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
          cut: true,
        })}
        onSiguiente={vi.fn()}
      />,
    );
    // No Vehículo: line when the parent couldn't resolve the name
    // (defensive — the API doesn't carry uuid_tipo_vehiculo).
    expect(screen.queryByText(/Veh[íi]culo/i)).not.toBeInTheDocument();
  });

  it('calls bridge.imprimir with the payload from buildPrintPayload on Imprimir click', async () => {
    const buildPrintPayload = vi.fn((uuid_ingreso: string) => ({
      buffer: Buffer.from(`entrada:${uuid_ingreso}`).toString('base64'),
      ticketId: uuid_ingreso,
      cut: true,
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
      cut: true,
    });
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
          cut: true,
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

  // HU-INGRESO-SIN-PLACA (REQ-OPS-197) — `Identificación:` line.

  it('test_renders_con_placa_default_no_consecutivo (legacy carro/moto row, consecutivo undefined)', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
          cut: true,
        })}
        onSiguiente={vi.fn()}
      />,
    );
    // No `Identificación:` line when consecutivo is undefined.
    expect(screen.queryByTestId('tiquete-identificacion')).not.toBeInTheDocument();
    // Folio still rendered (the print-preview thumbnail repeats it
    // alongside the summary block below, so it legitimately appears twice).
    expect(
      screen.getAllByText(/11111111-1111-1111-1111-111111111111/).length,
    ).toBeGreaterThan(0);
  });

  it('test_renders_identificacion_with_consecutivo (REQ-OPS-197)', () => {
    render(
      <TiqueteModal
        open
        uuid_ingreso="11111111-1111-1111-1111-111111111111"
        tipo_entrada="ROTACION"
        consecutivo="BICI-000001-3f8a1b2c"
        buildPrintPayload={() => ({
          buffer: 'AA==',
          ticketId: 'ticket-1',
          cut: true,
        })}
        onSiguiente={vi.fn()}
      />,
    );
    const idLine = screen.getByTestId('tiquete-identificacion');
    expect(idLine).toHaveTextContent(/Identificación/);
    expect(idLine).toHaveTextContent(/BICI-000001-3f8a1b2c/);
    // Folio also rendered (always; appears in both the preview
    // thumbnail and the summary block below it).
    expect(
      screen.getAllByText(/11111111-1111-1111-1111-111111111111/).length,
    ).toBeGreaterThan(0);
  });
});
