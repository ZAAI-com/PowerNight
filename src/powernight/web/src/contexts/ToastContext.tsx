import React, { createContext, useCallback, useContext, useEffect, useRef, useState, ReactNode } from 'react';

export type ToastVariant = 'success' | 'error';

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
}

interface ToastContextType {
  showToast: (message: string, variant?: ToastVariant) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

const TOAST_DURATION_MS = 4000;

interface ToastProviderProps {
  children: ReactNode;
}

export const ToastProvider: React.FC<ToastProviderProps> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextIdRef = useRef(0);
  const timeoutsRef = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  // Clear any pending auto-dismiss timers on unmount
  useEffect(() => {
    const timeouts = timeoutsRef.current;
    return () => {
      timeouts.forEach((timeoutId) => clearTimeout(timeoutId));
      timeouts.clear();
    };
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (message: string, variant: ToastVariant = 'success') => {
      const id = nextIdRef.current++;
      setToasts((prev) => [...prev, { id, message, variant }]);

      const timeoutId = setTimeout(() => {
        timeoutsRef.current.delete(timeoutId);
        dismissToast(id);
      }, TOAST_DURATION_MS);
      timeoutsRef.current.add(timeoutId);
    },
    [dismissToast]
  );

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}

      {/* Toast container (top-right, below the fixed header) */}
      <div
        className="fixed top-20 right-4 z-[60] flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]"
        role="status"
        aria-live="polite"
        data-testid="toast-container"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`flex items-start justify-between gap-3 p-4 rounded-md border shadow-lg ${
              toast.variant === 'success'
                ? 'bg-green-50 border-green-200 text-green-800'
                : 'bg-red-50 border-red-200 text-red-800'
            }`}
          >
            <p className="text-sm break-words">{toast.message}</p>
            <button
              type="button"
              onClick={() => dismissToast(toast.id)}
              aria-label="Dismiss notification"
              className={`flex-shrink-0 text-lg leading-none focus:outline-none ${
                toast.variant === 'success'
                  ? 'text-green-600 hover:text-green-800'
                  : 'text-red-600 hover:text-red-800'
              }`}
            >
              &times;
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useToast = (): ToastContextType => {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
