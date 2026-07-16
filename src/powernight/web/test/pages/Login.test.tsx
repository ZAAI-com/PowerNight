import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import Login from '../../src/pages/Login';


describe('Login', () => {
  it('submits the configured PowerNight API key', async () => {
    const onLogin = vi.fn().mockResolvedValue(true);
    const onClearError = vi.fn();
    render(
      <Login
        onLogin={onLogin}
        onClearError={onClearError}
      />
    );

    fireEvent.change(screen.getByPlaceholderText('Enter your API key'), {
      target: { value: '  test-key  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith('test-key'));
    expect(onClearError).toHaveBeenCalledOnce();
  });

  it('displays authentication errors and blocks an empty submission', () => {
    const onLogin = vi.fn().mockResolvedValue(false);
    render(
      <Login
        error="Invalid API key"
        onLogin={onLogin}
        onClearError={vi.fn()}
      />
    );

    expect(screen.getByText('Authentication Error')).toBeInTheDocument();
    expect(screen.getByText('Invalid API key')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign In' })).toBeDisabled();
    expect(onLogin).not.toHaveBeenCalled();
  });
});
