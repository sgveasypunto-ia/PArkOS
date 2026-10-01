import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { resetPassword, updateUsuario } from '../api/usuariosApi';
import { usuarioUpdateSchema, type Usuario, type UsuarioUpdate } from '../api/usuariosSchema';
import { useSWRConfig } from 'swr';

interface UsuarioFormProps {
  usuario: Usuario;
}

export function UsuarioForm({ usuario }: UsuarioFormProps) {
  const { mutate } = useSWRConfig();
  const navigate = useNavigate();

  // Held in component state, never in storage: the backend returns the
  // plaintext exactly once, so persisting it would leak a live credential
  // into localStorage or a URL.
  const [tempPassword, setTempPassword] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<UsuarioUpdate>({
    resolver: zodResolver(usuarioUpdateSchema),
    defaultValues: {
      email: usuario.email,
      nombre: usuario.nombre ?? '',
      apellido: usuario.apellido ?? '',
      cedula: usuario.cedula ?? '',
      rol: usuario.rol,
    },
  });

  const onSubmit = async (data: UsuarioUpdate) => {
    try {
      const updated = await updateUsuario(usuario.uuid, data);

      // `update_admin_usuario` goes through `close_and_insert`, which
      // regenerates the PK for the new bi-temporal version. The endpoint
      // keeps serving the row only at the NEW uuid, and
      // `GET /usuarios/{uuid}` filters `vigente_hasta IS NULL`, so the
      // previous uuid 404s from here on. Staying on the stale url would
      // leave the detail page permanently broken after any edit.
      if (updated.uuid !== usuario.uuid) {
        await mutate(`usuario-${usuario.uuid}`, updated, { revalidate: false });
        navigate(`/admin/usuarios/${updated.uuid}`, { replace: true });
        return;
      }

      await mutate(`usuario-${usuario.uuid}`);
      alert('Usuario actualizado correctamente');
    } catch (error) {
      alert(
        `Error al actualizar usuario: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  const onResetPassword = async () => {
    if (!window.confirm('¿Resetear la contraseña de este usuario?')) {
      return;
    }
    try {
      const result = await resetPassword(usuario.uuid);
      setTempPassword(result.temporary_password);
    } catch (error) {
      alert(
        `Error al resetear contraseña: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-2xl">
      <div>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" {...register('email')} />
        {errors.email && (
          <p className="text-sm text-red-600 mt-1">{errors.email.message}</p>
        )}
      </div>

      <div>
        <Label htmlFor="nombre">Nombre</Label>
        <Input id="nombre" {...register('nombre')} />
      </div>

      <div>
        <Label htmlFor="apellido">Apellido</Label>
        <Input id="apellido" {...register('apellido')} />
      </div>

      <div>
        <Label htmlFor="cedula">Cédula</Label>
        <Input id="cedula" {...register('cedula')} />
      </div>

      <div>
        <Label htmlFor="rol">Rol</Label>
        <Input id="rol" {...register('rol')} />
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Guardando...' : 'Guardar cambios'}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => void onResetPassword()}
          data-testid="reset-password-btn"
        >
          Resetear contraseña
        </Button>
      </div>

      <Dialog
        open={tempPassword !== null}
        onOpenChange={(open) => {
          if (!open) setTempPassword(null);
        }}
      >
        <DialogContent data-testid="temp-password-dialog">
          <DialogHeader>
            <DialogTitle>Contraseña temporal generada</DialogTitle>
            <DialogDescription>
              Esta contraseña se muestra una sola vez. Entrégasela al
              operador por un canal fuera de banda; no se guarda en
              ningún lado.
            </DialogDescription>
          </DialogHeader>

          <p
            className="rounded border bg-muted px-3 py-2 font-mono text-sm tracking-wide"
            data-testid="temp-password-value"
          >
            {tempPassword}
          </p>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              data-testid="temp-password-close"
              onClick={() => setTempPassword(null)}
            >
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </form>
  );
}
