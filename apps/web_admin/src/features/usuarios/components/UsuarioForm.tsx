import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { updateUsuario } from '../api/usuariosApi';
import { usuarioUpdateSchema, type Usuario, type UsuarioUpdate } from '../api/usuariosSchema';
import { useSWRConfig } from 'swr';

interface UsuarioFormProps {
  usuario: Usuario;
}

export function UsuarioForm({ usuario }: UsuarioFormProps) {
  const { mutate } = useSWRConfig();

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
      await updateUsuario(usuario.uuid, data);
      await mutate(`usuario-${usuario.uuid}`);
      alert('Usuario actualizado correctamente');
    } catch (error) {
      alert('Error al actualizar usuario');
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

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Guardando...' : 'Guardar cambios'}
      </Button>
    </form>
  );
}
