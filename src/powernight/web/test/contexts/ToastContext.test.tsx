import React from 'react';
import { vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ToastProvider, useToast, ToastVariant } from '../../src/contexts/ToastContext';

const ToastTrigger: React.FC<{ message: string; variant?: ToastVariant }> = ({ message, variant }) => {
  const { showToast } = useToast();
  return (
    <button onClick={() => showToast(message, variant)}>Show Toast</button>
  );
};

describe('ToastContext', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a success toast when showToast is called', () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Task created" variant="success" />
      </ToastProvider>
    );

    expect(screen.queryByText('Task created')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Show Toast'));

    const toast = screen.getByText('Task created');
    expect(toast).toBeInTheDocument();
    expect(toast.closest('div')).toHaveClass('bg-green-50');
  });

  it('renders an error toast with error styling', () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Something failed" variant="error" />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Toast'));

    const toast = screen.getByText('Something failed');
    expect(toast).toBeInTheDocument();
    expect(toast.closest('div')).toHaveClass('bg-red-50');
  });

  it('auto-dismisses the toast after 4 seconds', () => {
    vi.useFakeTimers();

    render(
      <ToastProvider>
        <ToastTrigger message="Auto dismiss me" />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Toast'));
    expect(screen.getByText('Auto dismiss me')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(4000);
    });

    expect(screen.queryByText('Auto dismiss me')).not.toBeInTheDocument();
  });

  it('dismisses the toast when the close button is clicked', () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Close me" />
      </ToastProvider>
    );

    fireEvent.click(screen.getByText('Show Toast'));
    expect(screen.getByText('Close me')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Dismiss notification'));

    expect(screen.queryByText('Close me')).not.toBeInTheDocument();
  });

  it('throws when useToast is used outside a ToastProvider', () => {
    // Silence React error boundary noise for the expected throw
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(() => render(<ToastTrigger message="No provider" />)).toThrow(
      'useToast must be used within a ToastProvider'
    );

    consoleError.mockRestore();
  });
});
