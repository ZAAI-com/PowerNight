import { useEffect, useRef } from 'react';

/** Non-overlapping, visibility-aware polling. Zero disables repeated polling. */
export function usePolling(callback: () => Promise<void>, intervalMs: number) {
  const inFlight = useRef(false);
  const callbackRef = useRef(callback);
  useEffect(() => { callbackRef.current = callback; }, [callback]);
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    const schedule = () => {
      window.clearTimeout(timer);
      if (!cancelled && intervalMs > 0 && document.visibilityState !== 'hidden') timer = window.setTimeout(tick, intervalMs);
    };
    const tick = async () => {
      if (cancelled) return;
      try {
        if (!inFlight.current && document.visibilityState !== 'hidden') {
          inFlight.current = true;
          try { await callbackRef.current(); } finally { inFlight.current = false; }
        }
      } catch (error) {
        console.error('Polling request failed:', error);
      } finally { schedule(); }
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') window.clearTimeout(timer);
      else if (intervalMs > 0) void tick();
    };
    void tick();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [intervalMs]);
}
