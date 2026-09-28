import { useAuthStore } from '@parkos/ui-kit/store';

/**
 * WaitForAuth — blocks rendering until Zustand persist rehydrates.
 *
 * Uses a Zustand selector on `hasRehydrated` so the component re-renders
 * exactly once (false → true) and never re-renders on subsequent store
 * mutations (setTokens, clear, etc.). No useEffect, no useState, no
 * subscribe, no useMemo — just the selector.
 */
export function WaitForAuth({ children }: { children: React.ReactNode }) {
  const hasRehydrated = useAuthStore((s) => s.hasRehydrated);

  if (!hasRehydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
