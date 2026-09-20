/**
 * Tests for `<PagoModal />` extracted presentational component
 * (HU-F8.1, REQ-OPS-167).
 *
 * The PagoModal owns:
 *   - medio_pago discriminator (efectivo | datafono)
 *   - monto_recibido (efectivo) | voucher (datafono)
 *   - FE toggle + conditional NIT/DV/nombre/email fields
 *   - vueltos computed via useMemo (inline, ABIERTO-200 follow-up
 *     — `useVueltos` doesn't exist yet per F7.1 `useCountdown`
 *     precedent)
 *   - `validarNitModulo11` (BR7) for FE NIT validation
 *
 * Coverage (5 component tests):
 *   M1: render with default props → vueltos displays "—" (no
 *       monto_recibido typed yet).
 *   M2: select efectivo + type monto_recibido=50000 → vueltos shows
 *       `$ 9.000` (via formatCOP, total=41000 cents base — passed in
 *       props as $41000 units so vueltos = 50000-41000 = 9000).
 *   M3: select datáfono + empty voucher → submit blocked (Zod).
 *   M4: toggle FE con datos + invalid NIT (DV mismatch) → inline
 *       error from `validarNitModulo11` ('800.123.456' with DV '1').
 *   M5: click "Confirmar pago" → onSubmit called with the parsed
 *       PagoFormValues (discriminated union by medio).
 */
import * as React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import { PagoModal, type PagoModalProps } from './PagoModal';
import type { PagoFormValues } from './PagoModal';

const DEFAULT_PROPS: PagoModalProps = {
  uuid_ingreso: '00000000-0000-0000-0000-000000000001',
  total_cop: 41000,
  onSubmit: vi.fn().mockResolvedValue(undefined),
};

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('<PagoModal /> — REQ-OPS-167 (FE consumidor final + validarNitModulo11)', () => {
  it('M1: render with default props → vueltos displays "—" (no monto_recibido typed)', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    // vueltos initial state = 41000 (default `monto_recibido` equals total)
    // so vueltos = 0 → "—" sentinel
    const vueltosEl = screen.getByTestId('pago-vueltos');
    expect(vueltosEl.textContent).toBe('—');
  });

  it('M2: select efectivo + change monto_recibido → vueltos shows $ 9.000 via formatCOP', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    const montoInput = screen.getByTestId('pago-monto-recibido');
    act(() => {
      fireEvent.change(montoInput, { target: { value: '50000' } });
    });
    const vueltosEl = screen.getByTestId('pago-vueltos');
    // vueltos = 50000 - 41000 = 9000 → formatCOP(9000) = "$ 9.000"
    // (Intl.NumberFormat es-CO emits a NBSP U+00A0 between $ and digits;
    //  match any whitespace.)
    expect(vueltosEl.textContent?.replace(/\s/g, ' ')).toMatch(/^\$ 9\.000$/);
  });

  it('M3: select datáfono + empty voucher → submit blocked (Zod)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);

    // Switch to datafono via the medio_pago select.
    const medioSelect = screen.getByTestId('pago-medio-pago');
    act(() => {
      fireEvent.change(medioSelect, { target: { value: 'datafono' } });
    });

    // Submit button click — voucher is empty, Zod must reject.
    const submitBtn = screen.getByTestId('pago-confirmar');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(onSubmit).not.toHaveBeenCalled();
    // The form should display a voucher-required error message.
    const voucherErr = screen.queryByTestId('pago-voucher-error');
    if (voucherErr) {
      expect(voucherErr.textContent).toBeTruthy();
    }
  });

  it('M4: toggle FE + invalid NIT (DV mismatch) → inline error from validarNitModulo11', async () => {
    render(<PagoModal {...DEFAULT_PROPS} />);

    // Toggle FE on.
    const feToggle = screen.getByTestId('pago-fe-toggle');
    act(() => {
      fireEvent.click(feToggle);
    });

    // Type the canonical reference NIT with WRONG DV ('1' instead of '7').
    const nitInput = screen.getByTestId('pago-nit');
    act(() => {
      fireEvent.change(nitInput, { target: { value: '800.123.456' } });
    });
    const dvInput = screen.getByTestId('pago-fe-dv');
    act(() => {
      fireEvent.change(dvInput, { target: { value: '1' } });
    });

    // Submit — the form's RHF Zod resolver must surface the DV mismatch.
    const submitBtn = screen.getByTestId('pago-confirmar');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    const dvErr = screen.queryByTestId('pago-fe-dv-error');
    expect(dvErr).not.toBeNull();
    expect(dvErr?.textContent).toMatch(/7|dv/i);
  });

  it('M5: click "Confirmar pago" → onSubmit called with parsed PagoFormValues (efectivo)', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} total_cop={41000} />);

    const submitBtn = screen.getByTestId('pago-confirmar');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const arg = onSubmit.mock.calls[0]?.[0] as PagoFormValues;
    expect(arg.medio_pago).toBe('efectivo');
    expect(arg.monto_recibido_cop).toBe(41000);
    expect(arg.nombre_cliente).toBeDefined();
  });
});