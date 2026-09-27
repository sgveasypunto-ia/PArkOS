import { useEffect, useState } from 'react';
import { useAuthStore, type AuthState } from '@parkos/ui-kit/store';

export function WaitForAuth({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancel = false;
    const unsub = useAuthStore.subscribe((state: AuthState) => {
      if (!cancel && state.hasRehydrated) {
        setReady(true);
      }
    });
    if (useAuthStore.getState().hasRehydrated) {
      setReady(true);
    }
    return () => {
      cancel = true;
      unsub();
    };
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
