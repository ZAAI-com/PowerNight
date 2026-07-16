import React from 'react';
import { vi, type Mocked } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Planner from '../../src/pages/Planner';
import { ToastProvider } from '../../src/contexts/ToastContext';
import { api } from '../../src/utils/api';

// Mock the API
vi.mock('../../src/utils/api', () => ({
  api: {
    getTasks: vi.fn(),
    getTaskCommands: vi.fn(),
    getTaskPresets: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    deleteTask: vi.fn(),
    toggleTask: vi.fn(),
    executeTask: vi.fn(),
    getTaskExecution: vi.fn(),
  },
}));

const mockApi = api as Mocked<typeof api>;

const renderPlanner = () =>
  render(
    <ToastProvider>
      <Planner />
    </ToastProvider>
  );

describe('Planner', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockApi.getTasks.mockResolvedValue({ tasks: [], total: 0 });
    mockApi.getTaskPresets.mockResolvedValue({ presets: [], total: 0 });
    mockApi.getTaskCommands.mockResolvedValue({
      commands: {
        reserve: {
          description: 'Set backup reserve percentage',
          params: {
            percentage: {
              type: 'number',
              required: true,
              min: 0,
              max: 100,
              unit: '%',
            },
          },
        },
      },
    });
  });

  const openCreateForm = async () => {
    // Wait for initial load to finish
    const createButton = await screen.findByRole('button', { name: 'Create Task' });
    fireEvent.click(createButton);
    await screen.findByText('Create New Task');
  };

  it('blocks submit and shows an error when a required command param is missing', async () => {
    const { container } = renderPlanner();
    await openCreateForm();

    // Fill only the name; leave the required "percentage" param empty
    const nameInput = screen.getByRole('textbox');
    fireEvent.change(nameInput, { target: { value: 'Night reserve' } });

    const form = container.querySelector('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    expect(
      await screen.findByText(/Missing required parameter: percentage/i)
    ).toBeInTheDocument();
    expect(mockApi.createTask).not.toHaveBeenCalled();
  });

  it('submits the task once all required params are provided', async () => {
    mockApi.createTask.mockResolvedValue({
      id: 'task-1',
      name: 'Night reserve',
      time: '00:00',
      command: 'reserve',
      command_params: { percentage: 80 },
      enabled: true,
      execution_count: 0,
    });

    const { container } = renderPlanner();
    await openCreateForm();

    const nameInput = screen.getByRole('textbox');
    fireEvent.change(nameInput, { target: { value: 'Night reserve' } });

    const percentageInput = screen.getByRole('spinbutton');
    fireEvent.change(percentageInput, { target: { value: '80' } });

    const form = container.querySelector('form');
    fireEvent.submit(form!);

    await waitFor(() => {
      expect(mockApi.createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Night reserve',
          command: 'reserve',
          command_params: expect.objectContaining({ percentage: 80 }),
        })
      );
    });

    // Success feedback is shown via toast
    expect(await screen.findByText('Task "Night reserve" created')).toBeInTheDocument();
  });
});
