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
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) =>
      options?.defaultValue ?? key,
  }),
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

  it('M3b (bug fix, 2026-09-23): select datáfono + voucher filled → submit succeeds', async () => {
    // Regression: `pagoDatafonoSchema` declared an orphaned `total_cop`
    // field with no matching form control, so Zod validation ALWAYS
    // failed for datafono (even with a valid voucher) and `onSubmit`
    // never fired. M3 (empty voucher) never caught it because its
    // assertion — `onSubmit not called` — holds true either way.
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);

    act(() => {
      fireEvent.change(screen.getByTestId('pago-medio-pago'), { target: { value: 'datafono' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-voucher'), { target: { value: 'VOUCHER-123' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      medio_pago: 'datafono',
      voucher: 'VOUCHER-123',
    });
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
    if (arg.medio_pago === 'efectivo') {
      expect(arg.monto_recibido_cop).toBe(41000);
    }
    expect(arg.nombre_cliente).toBeDefined();
  });

  it('M6 (fix HU-F8.1-monto-insuficiente): efectivo + monto_recibido < total → submit blocked, onSubmit NOT called, vueltos "—"', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} total_cop={41000} />);

    // Type a monto_recibido inferior al total.
    const montoInput = screen.getByTestId('pago-monto-recibido');
    act(() => {
      fireEvent.change(montoInput, { target: { value: '5000' } });
    });

    // Submit click — debe estar bloqueado por el handler de HU-F8.1.
    const submitBtn = screen.getByTestId('pago-confirmar');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // El onSubmit NO debe haberse llamado: el cliente bloquea el submit
    // antes de tocar la red cuando monto_recibido_cop < total_cop.
    expect(onSubmit).not.toHaveBeenCalled();

    // El vueltos debe mostrar "—" porque 5000 < 41000.
    const vueltosEl = screen.getByTestId('pago-vueltos');
    expect(vueltosEl.textContent).toBe('—');
  });

  it('M7 (fix HU-F8.1-copy): el label del toggle FE usa el copy obligatorio de la spec ("a nombre del cliente ... consumidor final")', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    const feToggle = screen.getByTestId('pago-fe-toggle');
    // El FormLabel padre (sibling del checkbox) debe contener el copy
    // obligatorio de HU-F8.1 — "Factura a nombre del cliente (opcional);
    // por defecto, factura a consumidor final" (nunca "FE opcional" a secas).
    const label = feToggle.parentElement?.querySelector('label');
    expect(label?.textContent).toMatch(/a nombre del cliente/i);
    expect(label?.textContent).toMatch(/consumidor final/i);
    expect(label?.textContent).toMatch(/opcional/i);
  });
});