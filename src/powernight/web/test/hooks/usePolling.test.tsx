import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';
import { usePolling } from '../../src/hooks/usePolling';

describe('visibility-aware serial polling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('waits for completion before scheduling another request', async () => {
    let finish!: () => void;
    const callback = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
    const { unmount } = renderHook(() => usePolling(callback, 30000));
    await act(async () => { await vi.advanceTimersByTimeAsync(90000); });
    expect(callback).toHaveBeenCalledTimes(1);
    await act(async () => { finish(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(callback).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => { finish(); await vi.advanceTimersByTimeAsync(90000); });
    expect(callback).toHaveBeenCalledTimes(2);
  });

  it('pauses hidden tabs, resumes on visibility and disables repeats at zero', async () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get');
    const callback = vi.fn(async () => {});
    const { rerender, unmount } = renderHook(({ interval }) => usePolling(callback, interval), {
      initialProps: { interval: 30000 },
    });
    await act(async () => {});
    visibility.mockReturnValue('hidden');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => { await vi.advanceTimersByTimeAsync(90000); });
    expect(callback).toHaveBeenCalledTimes(1);
    visibility.mockReturnValue('visible');
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(callback).toHaveBeenCalledTimes(2);
    rerender({ interval: 0 });
    await act(async () => { await vi.advanceTimersByTimeAsync(90000); });
    const count = callback.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(90000); });
    expect(callback).toHaveBeenCalledTimes(count);
    unmount();
  });

  it('handles rejected callbacks and keeps polling', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const callback = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined);
    const { unmount } = renderHook(() => usePolling(callback, 20000));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(error).toHaveBeenCalledWith('Polling request failed:', expect.any(Error));
    await act(async () => { await vi.advanceTimersByTimeAsync(20000); });
    expect(callback).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('uses the latest callback without restarting the interval on rerenders', async () => {
    const first = vi.fn(async () => {});
    const second = vi.fn(async () => {});
    const { rerender, unmount } = renderHook(({ callback }) => usePolling(callback, 20000), {
      initialProps: { callback: first },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    rerender({ callback: second });
    await act(async () => { await vi.advanceTimersByTimeAsync(9999); });
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(second).toHaveBeenCalledTimes(1);
    unmount();
  });

});
