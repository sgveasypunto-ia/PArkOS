/**
 * `UsuarioCrear.test.tsx` — 3-step wizard tests (HU-F16.2).
 *
 * Pattern mirrors the former `AdminUsuarioForm.test.tsx` (now replaced
 * by this wizard for the CREATE flow): a `Harness` renders the real
 * component with real RHF + zodResolver instances per step so the
 * rendered tree exercises the same path as production. No external
 * wizard library -- `UsuarioCrear` is plain `useState<Step>` + one RHF
 * form per step, per the repo convention (no multi-step lib existed in
 * `apps/web_admin` before this change).
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { UsuarioCrear } from './UsuarioCrear';
import type { AdminUsuarioCreateInput } from '../api/adminUsuarioSchema';

const BRANCHES = [
  { uuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', nombre: 'Bogotá' },
  { uuid: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', nombre: 'Medellín' },
];

function Harness({
  onSubmit = vi.fn(),
  isSubmitting = false,
  submitError = null,
}: {
  onSubmit?: (values: AdminUsuarioCreateInput) => void;
  isSubmitting?: boolean;
  submitError?: string | null;
}) {
  return (
    <UsuarioCrear
      onSubmit={onSubmit}
      isSubmitting={isSubmitting}
      availableBranches={BRANCHES}
      submitError={submitError}
    />
  );
}

async function fillStep1(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByTestId('wizard-field-email'), 'op@parkos.local');
  await user.type(screen.getByTestId('wizard-field-password'), 'Pass1234word');
  await user.click(screen.getByTestId('wizard-step1-next'));
}

async function fillStep2(user: ReturnType<typeof userEvent.setup>, rol = 'operador') {
  await user.selectOptions(screen.getByTestId('wizard-field-rol'), rol);
  await user.click(screen.getByTestId('wizard-step2-next'));
}

describe('UsuarioCrear wizard', () => {
  it('renders step 1 (datos personales) first', () => {
    render(<Harness />);
    expect(screen.getByTestId('wizard-step-datos')).toBeInTheDocument();
    expect(screen.queryByTestId('wizard-step-rol')).not.toBeInTheDocument();
    expect(screen.queryByTestId('wizard-step-sucursales')).not.toBeInTheDocument();
  });

  it('blocks advancing from step 1 with an empty email (Zod)', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByTestId('wizard-field-password'), 'Pass1234word');
    await user.click(screen.getByTestId('wizard-step1-next'));
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-datos')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('wizard-step-rol')).not.toBeInTheDocument();
  });

  it('blocks advancing from step 1 with a short password (Zod, min 8)', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.type(screen.getByTestId('wizard-field-email'), 'op@parkos.local');
    await user.type(screen.getByTestId('wizard-field-password'), 'short');
    await user.click(screen.getByTestId('wizard-step1-next'));
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-datos')).toBeInTheDocument();
    });
  });

  it('advances datos -> rol -> sucursales and submits the merged payload', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await fillStep1(user);
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-rol')).toBeInTheDocument();
    });

    await fillStep2(user, 'admin');
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-sucursales')).toBeInTheDocument();
    });

    await user.click(
      screen.getByTestId(`wizard-sucursal-${BRANCHES[0]!.uuid}`),
    );
    await user.click(screen.getByTestId('wizard-submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    const values = onSubmit.mock.calls[0]?.[0] as AdminUsuarioCreateInput;
    expect(values.email).toBe('op@parkos.local');
    expect(values.password).toBe('Pass1234word');
    expect(values.rol).toBe('admin');
    expect(values.sucursales_asignadas).toEqual([BRANCHES[0]!.uuid]);
  });

  it('submits with sucursales_asignadas = [] when no branch is checked', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await fillStep1(user);
    await waitFor(() => screen.getByTestId('wizard-step-rol'));
    await fillStep2(user);
    await waitFor(() => screen.getByTestId('wizard-step-sucursales'));

    await user.click(screen.getByTestId('wizard-submit'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    const values = onSubmit.mock.calls[0]?.[0] as AdminUsuarioCreateInput;
    expect(values.sucursales_asignadas).toEqual([]);
  });

  it('"Atrás" goes back a step and preserves previously entered values', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);

    await fillStep1(user);
    await waitFor(() => screen.getByTestId('wizard-step-rol'));

    await user.click(screen.getByTestId('wizard-step2-back'));
    await waitFor(() => {
      expect(screen.getByTestId('wizard-step-datos')).toBeInTheDocument();
    });
    expect(screen.getByTestId('wizard-field-email')).toHaveValue('op@parkos.local');

    // Forward again (values already preserved — no need to retype) then
    // back from step 3 — rol should still be whatever step 2 set.
    await user.click(screen.getByTestId('wizard-step1-next'));
    await waitFor(() => screen.getByTestId('wizard-step-rol'));
    await fillStep2(user, 'admin');
    await waitFor(() => screen.getByTestId('wizard-step-sucursales'));
    await user.click(screen.getByTestId('wizard-step3-back'));
    await waitFor(() => screen.getByTestId('wizard-step-rol'));
    expect(screen.getByTestId('wizard-field-rol')).toHaveValue('admin');
  });

  it('renders the submission error on the sucursales step', async () => {
    const user = userEvent.setup();
    render(<Harness submitError="boom" />);

    await fillStep1(user);
    await waitFor(() => screen.getByTestId('wizard-step-rol'));
    await fillStep2(user);
    await waitFor(() => screen.getByTestId('wizard-step-sucursales'));

    expect(screen.getByRole('alert')).toHaveTextContent('boom');
  });

  it('disables the submit button while isSubmitting', async () => {
    const user = userEvent.setup();
    render(<Harness isSubmitting />);

    await fillStep1(user);
    await waitFor(() => screen.getByTestId('wizard-step-rol'));
    await fillStep2(user);
    await waitFor(() => screen.getByTestId('wizard-step-sucursales'));

    expect(screen.getByTestId('wizard-submit')).toBeDisabled();
  });
});
