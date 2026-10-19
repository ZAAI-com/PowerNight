import { useEffect, useRef, type ReactNode } from 'react';

export function PresetDialog({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  return (
    <dialog ref={ref} aria-labelledby="preset-dialog-title" onCancel={onClose}
      onClick={event => { if (event.target === event.currentTarget) onClose(); }}
      className="m-auto bg-white p-0 rounded-lg shadow-xl max-w-md w-full backdrop:bg-black/50">
      <div className="p-6">{children}</div>
    </dialog>
  );
}
