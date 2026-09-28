/**
 * `AdminUsuarioForm.test.tsx` — presentational tests (IT-1.4).
 *
 * Pattern (mirror of LoginForm.test.tsx): a `Harness` builds a real
 * RHF form with `zodResolver` so the rendered tree exercises the same
 * component path as production.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import { AdminUsuarioForm } from './AdminUsuarioForm';
import { adminUsuarioCreateSchema, type AdminUsuarioCreateInput } from '../api/adminUsuarioSchema';

const BRANCHES = [
  { uuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', nombre: 'Bogotá' },
  { uuid: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', nombre: 'Medellín' },
];

function Harness({
  branches = BRANCHES,
  onSubmit = vi.fn(),
}: {
  branches?: typeof BRANCHES;
  onSubmit?: (values: AdminUsuarioCreateInput) => void;
}) {
  const form = useForm<AdminUsuarioCreateInput>({
    resolver: zodResolver(adminUsuarioCreateSchema),
    defaultValues: {
      email: '',
      password: '',
      rol: 'operador',
      nombre: '',
      apellido: '',
      cedula: '',
      sucursales_asignadas: [],
    },
  });
  return (
    <AdminUsuarioForm
      form={form}
      onSubmit={onSubmit}
      isSubmitting={false}
      availableBranches={branches}
    />
  );
}

describe('AdminUsuarioForm', () => {
  it('renders the core fields', () => {
    render(<Harness />);
    expect(screen.getByTestId('admin-field-email')).toBeInTheDocument();
    expect(screen.getByTestId('admin-field-password')).toBeInTheDocument();
    expect(screen.getByTestId('admin-field-rol')).toBeInTheDocument();
  });

  it('rejects empty email (Zod)', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId('admin-field-password'), 'Pass1234word');
    await user.click(screen.getByTestId('admin-submit'));
    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('rejects short password (Zod)', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId('admin-field-email'), 'op@parkos.local');
    await user.type(screen.getByTestId('admin-field-password'), 'short');
    await user.click(screen.getByTestId('admin-submit'));
    await waitFor(() => {
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  it('renders optional fields only when toggle clicked (default hidden)', () => {
    render(<Harness />);
    expect(screen.queryByTestId('admin-field-nombre')).toBeNull();
  });

  it('calls onSubmit with parsed values when valid input', async () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const user = userEvent.setup();
    await user.type(screen.getByTestId('admin-field-email'), 'op@parkos.local');
    await user.type(screen.getByTestId('admin-field-password'), 'Pass1234word');
    await user.click(screen.getByTestId('admin-submit'));
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    const values = (onSubmit.mock.calls[0]?.[0] ?? {}) as AdminUsuarioCreateInput;
    expect(values.email).toBe('op@parkos.local');
    expect(values.password).toBe('Pass1234word');
    expect(values.rol).toBe('operador');
    expect(values.sucursales_asignadas).toEqual([]);
  });
});
