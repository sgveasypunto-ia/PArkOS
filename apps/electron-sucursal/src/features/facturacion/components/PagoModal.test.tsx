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
    const call = onSubmit.mock.calls[0];
    if (!call) throw new Error('onSubmit was not called');
    expect(call[0]).toMatchObject({
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

    // Type the canonical reference NIT with WRONG DV ('1' instead of '5').
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
    // El operador nunca ve el código crudo del esquema Zod.
    expect(dvErr?.textContent).not.toMatch(/dv_invalido/);
    expect(dvErr?.textContent).toMatch(/dígito de verificación/i);
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

  it('M5b (H2): onSubmit rejects -> inline error shown, no unhandled rejection, button re-enabled', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} total_cop={41000} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('pago-error')).not.toBeNull();
    expect(screen.getByTestId('pago-confirmar')).not.toHaveProperty('disabled', true);
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

  it('M7 (FE siempre): el aviso fijo dice que la FE se emite siempre a consumidor final por defecto; el checkbox solo elige facturar a nombre del cliente (opcional)', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    // Fixed notice: the electronic invoice is ALWAYS emitted (no operator decision).
    const aviso = screen.getByTestId('pago-fe-aviso');
    expect(aviso.textContent).toMatch(/se emite siempre/i);
    expect(aviso.textContent).toMatch(/consumidor final/i);
    // The checkbox only decides whether the customer's own data go on it.
    const feToggle = screen.getByTestId('pago-fe-toggle');
    const label = feToggle.parentElement?.querySelector('label');
    expect(label?.textContent).toMatch(/a nombre del cliente/i);
    expect(label?.textContent).toMatch(/opcional/i);
    expect(label?.textContent).not.toMatch(/generar/i);
  });

  it('M7b: feCheckboxLabel overrides the checkbox copy (subscription sale: bill the subscriber)', () => {
    render(<PagoModal {...DEFAULT_PROPS} feCheckboxLabel="Facturar a nombre del suscriptor (opcional)" />);
    const label = screen.getByTestId('pago-fe-toggle').parentElement?.querySelector('label');
    expect(label?.textContent).toBe('Facturar a nombre del suscriptor (opcional)');
  });

  it('M13b (PT-1): `draft` restores what was typed before stepping back; onDraftChange reports edits', () => {
    const onDraftChange = vi.fn();
    const { unmount } = render(<PagoModal {...DEFAULT_PROPS} onDraftChange={onDraftChange} />);
    act(() => {
      fireEvent.change(screen.getByTestId('pago-monto-recibido'), { target: { value: '50000' } });
    });
    const last = onDraftChange.mock.calls.at(-1)?.[0] as PagoFormValues;
    expect((last as { monto_recibido_cop: number }).monto_recibido_cop).toBe(50000);
    unmount();

    // Back -> forward: the host re-mounts the modal with the saved draft.
    render(<PagoModal {...DEFAULT_PROPS} draft={last} />);
    expect(screen.getByTestId('pago-vueltos').textContent?.replace(/\s/g, ' ')).toMatch(/^\$ 9\.000$/);
  });

  it('M14 (PT-1): a different total discards the draft (plan changed)', () => {
    const draft = { medio_pago: 'efectivo', monto_recibido_cop: 99999, fe: false } as Partial<PagoFormValues>;
    const { rerender } = render(<PagoModal {...DEFAULT_PROPS} draft={draft} />);
    rerender(<PagoModal {...DEFAULT_PROPS} total_cop={30000} draft={draft} />);
    // Reset to the new total: nothing left over to give back.
    expect(screen.getByTestId('pago-vueltos').textContent).toBe('—');
  });

  it('M15: re-rendering with a NEW clientePrefill object never wipes what the operator typed', () => {
    const { rerender } = render(
      <PagoModal {...DEFAULT_PROPS} clientePrefill={{ nit: '900123456', nombre: 'ACME', fe: true }} />,
    );
    act(() => {
      fireEvent.change(screen.getByTestId('pago-fe-email'), { target: { value: 'a@b.co' } });
    });
    rerender(<PagoModal {...DEFAULT_PROPS} clientePrefill={{ nit: '900123456', nombre: 'ACME', fe: true }} />);
    expect((screen.getByTestId('pago-fe-email') as HTMLInputElement).value).toBe('a@b.co');
  });

  it('M8 (persona/empresa): checkbox marcado arranca en "empresa"/NIT sin ningún valor precargado (solo placeholder)', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    act(() => {
      fireEvent.click(screen.getByTestId('pago-fe-toggle'));
    });

    const tipoPersonaSelect = screen.getByTestId('pago-tipo-persona') as HTMLSelectElement;
    expect(tipoPersonaSelect.value).toBe('empresa');
    // No hay selector de tipo de documento para empresa (siempre NIT).
    expect(screen.queryByTestId('pago-tipo-documento')).toBeNull();

    const nitInput = screen.getByTestId('pago-nit') as HTMLInputElement;
    const nombreInput = screen.getByTestId('pago-fe-nombre') as HTMLInputElement;
    // BUGFIX 2026-09-25: value vacío, NUNCA el sentinel de consumidor
    // final precargado — el placeholder es solo un ejemplo cosmético.
    expect(nitInput.value).toBe('');
    expect(nitInput.placeholder).not.toBe('');
    expect(nitInput.placeholder).not.toMatch(/^2{15}$/);
    expect(nombreInput.value).toBe('');
  });

  it('M9 (persona natural): cambiar a "persona" muestra selector de tipo de documento + apellido, oculta DV', () => {
    render(<PagoModal {...DEFAULT_PROPS} />);
    act(() => {
      fireEvent.click(screen.getByTestId('pago-fe-toggle'));
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-tipo-persona'), { target: { value: 'persona' } });
    });

    const tipoDocumentoSelect = screen.getByTestId('pago-tipo-documento') as HTMLSelectElement;
    expect(tipoDocumentoSelect.value).toBe('CC');
    expect(screen.getByTestId('pago-fe-apellido')).toBeTruthy();
    // DV (módulo 11) es un concepto exclusivo de NIT — no debe pedirse
    // para persona natural (CC/CE/pasaporte no tienen dígito de
    // verificación en Colombia).
    expect(screen.queryByTestId('pago-fe-dv')).toBeNull();
  });

  it('M10 (persona natural, CC): submit con CC + nombre + apellido válidos llama onSubmit con tipo_identificador="CC"', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);
    act(() => {
      fireEvent.click(screen.getByTestId('pago-fe-toggle'));
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-tipo-persona'), { target: { value: 'persona' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-nit'), { target: { value: '1020304050' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-fe-nombre'), { target: { value: 'Juan' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-fe-apellido'), { target: { value: 'Pérez' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const arg = onSubmit.mock.calls[0]?.[0] as PagoFormValues & {
      tipo_persona: string;
      tipo_identificador: string;
      apellido?: string;
    };
    expect(arg.tipo_persona).toBe('persona');
    expect(arg.tipo_identificador).toBe('CC');
    expect(arg.apellido).toBe('Pérez');
  });

  it('M11 (persona natural, CC inválida): submit bloqueado por formato de documento', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);
    act(() => {
      fireEvent.click(screen.getByTestId('pago-fe-toggle'));
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-tipo-persona'), { target: { value: 'persona' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-nit'), { target: { value: '12' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-fe-nombre'), { target: { value: 'Juan' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-fe-apellido'), { target: { value: 'Pérez' } });
    });

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('M13 (HU-F9.1 paso 5, identificacionReadonly): con clientePrefill + identificacionReadonly, el bloque de identificación queda deshabilitado y el submit no exige re-validar DV', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <PagoModal
        {...DEFAULT_PROPS}
        onSubmit={onSubmit}
        clientePrefill={{
          nit: '900123456',
          nombre: 'ACME',
          fe: true,
          tipo_persona: 'empresa',
          tipo_identificador: 'NIT',
        }}
        identificacionReadonly
      />,
    );

    expect((screen.getByTestId('pago-tipo-persona') as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId('pago-nit') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId('pago-fe-nombre') as HTMLInputElement).disabled).toBe(true);
    // Sin DV precargado (el paso 1 de <Venta> no lo pide) — con el
    // bloque en solo-lectura no debe aparecer ningún error de DV que
    // bloquee el submit sobre un campo que el operador no puede editar.
    expect(screen.queryByTestId('pago-fe-dv-error')?.textContent).toBeFalsy();

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('M12 (checkbox off): sin tocar el bloque FE, submit pasa igual (cliente genérico) sin exigir nit/nombre/apellido', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);

    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const arg = onSubmit.mock.calls[0]?.[0] as PagoFormValues;
    expect(arg.fe).toBe(false);
  });

  it('M6 (caja bug 3): 422 voucher_datafono_duplicado se muestra junto al campo voucher, accesible y con foco', async () => {
    const err = Object.assign(new Error('http'), {
      status: 422,
      body: JSON.stringify({
        detail: {
          error: 'voucher_datafono_duplicado',
          message: 'El voucher TEST999 ya fue registrado hoy en esta sucursal.',
          referencia: 'TEST999',
        },
      }),
    });
    const onSubmit = vi.fn().mockRejectedValue(err);
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);

    act(() => {
      fireEvent.change(screen.getByTestId('pago-medio-pago'), { target: { value: 'datafono' } });
    });
    act(() => {
      fireEvent.change(screen.getByTestId('pago-voucher'), { target: { value: 'TEST999' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });

    const msg = screen.getByTestId('pago-voucher-error');
    expect(msg.textContent).toContain('TEST999 ya fue registrado');
    const input = screen.getByTestId('pago-voucher');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(input.getAttribute('aria-describedby')).toContain(msg.id);
    expect(document.activeElement).toBe(input);
    // No se duplica como error generico del formulario.
    expect(screen.queryByTestId('pago-error')).toBeNull();
  });

  it('M7: otros errores del submit siguen mostrando el error generico', async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error('boom'));
    render(<PagoModal {...DEFAULT_PROPS} onSubmit={onSubmit} />);
    await act(async () => {
      fireEvent.click(screen.getByTestId('pago-confirmar'));
    });
    expect(screen.getByTestId('pago-error')).toBeTruthy();
  });
});
