import React, { useState, useEffect } from 'react';
import { Task, CommandType, CommandDefinition, TaskFormData } from '../types';
import { api } from '../utils/api';
import LoadingSpinner from '../components/LoadingSpinner';
import StatusBadge from '../components/StatusBadge';
import { formatDate } from '../utils/helpers';

const Planner: React.FC = () => {
  console.log('Planner component is rendering!');

  const [tasks, setTasks] = useState<Task[]>([]);
  const [commands, setCommands] = useState<Record<string, CommandDefinition>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  
  // Execution tracking state
  const [executingTasks, setExecutingTasks] = useState<Record<string, string>>({}); // taskId -> executionId

  // Form state
  const [formData, setFormData] = useState<TaskFormData>({
    name: '',
    time: '00:00',
    command: 'reserve',
    command_params: {},
    enabled: true,
  });

  // Load tasks and available commands
  useEffect(() => {
    console.log('Planner component useEffect running');
    loadTasks();
    loadCommands();
  }, []);

  const loadTasks = async () => {
    try {
      setLoading(true);
      setError(null);
      const tasksData = await api.getTasks();
      setTasks(tasksData.tasks || []);
    } catch (err) {
      console.error('Failed to load tasks:', err);
      setError(err instanceof Error ? err.message : 'Failed to load tasks');
      setTasks([]);
    } finally {
      setLoading(false);
    }
  };

  const loadCommands = async () => {
    try {
      const commandsData = await api.getTaskCommands();
      setCommands(commandsData.commands || {});
    } catch (err) {
      console.error('Failed to load commands:', err);
      setCommands({});
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    try {
      setError(null);

      // Basic validation
      if (!formData.name.trim()) {
        setError('Name is required');
        return;
      }

      if (!formData.time) {
        setError('Time is required');
        return;
      }

      console.log('Submitting form data:', formData);

      if (editingTask) {
        // Update existing task
        await api.updateTask(editingTask.id, formData);
      } else {
        // Create new task
        await api.createTask(formData);
      }

      // Reload tasks
      await loadTasks();

      // Reset form
      resetForm();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred';
      setError(editingTask ? `Failed to update task: ${errorMessage}` : `Failed to create task: ${errorMessage}`);
      console.error('Form submission error:', err);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this task?')) {
      return;
    }
    
    try {
      await api.deleteTask(id);
      await loadTasks();
    } catch (err) {
      setError('Failed to delete task');
      console.error(err);
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await api.toggleTask(id);
      await loadTasks();
    } catch (err) {
      setError('Failed to toggle task');
      console.error(err);
    }
  };

  const handleExecute = async (id: string) => {
    try {
      // Start async execution
      const result = await api.executeTask(id);
      
      // Store execution ID and start polling
      setExecutingTasks(prev => ({ ...prev, [id]: result.execution_id }));
      
      // Start polling for status updates
      pollExecutionStatus(id, result.execution_id);
      
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to execute task';
      setError(errorMessage);
    }
  };

  const pollExecutionStatus = async (taskId: string, executionId: string) => {
    const pollInterval = 2000; // Poll every 2 seconds
    const maxPolls = 45; // Max 90 seconds (45 * 2s)
    let pollCount = 0;

    const poll = async () => {
      try {
        const execution = await api.getTaskExecution(taskId, executionId);
        
        // Check if execution is complete
        if (execution.status === 'success' || execution.status === 'error') {
          // Remove from executing tasks
          setExecutingTasks(prev => {
            const newState = { ...prev };
            delete newState[taskId];
            return newState;
          });
          
          // Show result
          if (execution.status === 'success') {
            alert(execution.result?.message || 'Task executed successfully');
          } else {
            alert(`Task execution failed: ${execution.error_message || 'Unknown error'}`);
          }
          
          // Reload tasks to update status
          await loadTasks();
          return;
        }
        
        // Continue polling if not complete and under limit
        pollCount++;
        if (pollCount < maxPolls) {
          setTimeout(poll, pollInterval);
        } else {
          // Timeout - remove from executing tasks
          setExecutingTasks(prev => {
            const newState = { ...prev };
            delete newState[taskId];
            return newState;
          });
          setError('Task execution timed out after 90 seconds');
        }
        
      } catch (err) {
        console.error('Error polling execution status:', err);
        // Remove from executing tasks on error
        setExecutingTasks(prev => {
          const newState = { ...prev };
          delete newState[taskId];
          return newState;
        });
        setError('Failed to check execution status');
      }
    };

    // Start polling
    setTimeout(poll, pollInterval);
  };

  const handleEdit = (task: Task) => {
    setEditingTask(task);
    setFormData({
      name: task.name,
      time: task.time,
      command: task.command,
      command_params: task.command_params,
      enabled: task.enabled,
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setFormData({
      name: '',
      time: '00:00',
      command: 'reserve',
      command_params: {},
      enabled: true,
    });
    setEditingTask(null);
    setShowForm(false);
  };

  const handleCommandChange = (command: CommandType) => {
    setFormData({
      ...formData,
      command,
      command_params: {}, // Reset params when command changes
    });
  };

  const handleParamChange = (paramName: string, value: any) => {
    setFormData({
      ...formData,
      command_params: {
        ...formData.command_params,
        [paramName]: value,
      },
    });
  };

  const renderCommandParams = () => {
    const commandDef = commands[formData.command];
    if (!commandDef || Object.keys(commandDef.params).length === 0) {
      return null;
    }

    return (
      <div className="space-y-4">
        <h4 className="text-sm font-medium text-gray-700">Command Parameters</h4>
        {Object.entries(commandDef.params).map(([paramName, paramDef]) => (
          <div key={paramName}>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {paramName.charAt(0).toUpperCase() + paramName.slice(1)}
              {paramDef.required && <span className="text-red-500 ml-1">*</span>}
            </label>
            
            {paramDef.type === 'boolean' ? (
              <select
                value={formData.command_params[paramName] ? 'true' : 'false'}
                onChange={(e) => handleParamChange(paramName, e.target.value === 'true')}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="true">On</option>
                <option value="false">Off</option>
              </select>
            ) : paramDef.options ? (
              <select
                value={formData.command_params[paramName] || ''}
                onChange={(e) => handleParamChange(paramName, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required={paramDef.required}
              >
                <option value="">Select {paramName}</option>
                {paramDef.options.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            ) : paramDef.type === 'number' ? (
              <input
                type="number"
                value={formData.command_params[paramName] || ''}
                onChange={(e) => handleParamChange(paramName, parseFloat(e.target.value))}
                min={paramDef.min}
                max={paramDef.max}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required={paramDef.required}
              />
            ) : (
              <input
                type="text"
                value={formData.command_params[paramName] || ''}
                onChange={(e) => handleParamChange(paramName, e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required={paramDef.required}
              />
            )}
            
            {paramDef.unit && (
              <span className="text-sm text-gray-500 ml-2">{paramDef.unit}</span>
            )}
          </div>
        ))}
      </div>
    );
  };

  if (loading) {
    return <LoadingSpinner />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Planner</h1>
              <p className="mt-1 text-sm text-gray-600">
                Manage automated tasks for your Powerwall
              </p>
            </div>
            <button
              onClick={() => setShowForm(!showForm)}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {showForm ? 'Cancel' : 'Create Task'}
            </button>
          </div>

          {/* Error Display */}
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800">{error}</p>
            </div>
          )}

          {/* Form */}
          {showForm && (
            <div className="mb-6 bg-white p-6 rounded-lg shadow-sm border border-gray-200">
              <h2 className="text-xl font-semibold mb-4">
                {editingTask ? 'Edit Task' : 'Create New Task'}
              </h2>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Time (24h format) <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="time"
                    value={formData.time}
                    onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    step="60"
                    pattern="[0-9]{2}:[0-9]{2}"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Command <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formData.command}
                    onChange={(e) => handleCommandChange(e.target.value as CommandType)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  >
                    {Object.entries(commands || {}).map(([cmd, def]) => (
                      <option key={cmd} value={cmd}>
                        {cmd} - {def?.description || cmd}
                      </option>
                    ))}
                  </select>
                </div>

                {renderCommandParams()}

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    checked={formData.enabled}
                    onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label className="ml-2 block text-sm text-gray-700">
                    Enabled
                  </label>
                </div>

                <div className="flex gap-2">
                  <button
                    type="submit"
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {editingTask ? 'Update' : 'Create'}
                  </button>
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-500"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Tasks List */}
          <div className="bg-white rounded-lg shadow-sm border border-gray-200">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold">Tasks</h2>
            </div>
            
            {tasks.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                No tasks configured. Create one to get started!
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Name
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Time
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Command
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Last Execution
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {tasks.map((task) => (
                      <tr key={task.id}>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">{task.name}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {task.time}
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-900">
                          {task.command_params && Object.keys(task.command_params).length > 0 ? (
                            <div className="text-xs">
                              {Object.entries(task.command_params).map(([key, value]) => (
                                <div key={key} className="whitespace-nowrap">
                                  <span className="font-medium">{key}:</span> {String(value)}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <StatusBadge
                            status={task.enabled ? 'enabled' : 'disabled'}
                          />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {executingTasks[task.id] ? (
                            <div>
                              <div className="text-blue-600 font-medium">Executing...</div>
                              <StatusBadge status="warning" />
                            </div>
                          ) : task.last_execution ? (
                            <div>
                              <div className="font-mono text-xs">{formatDate(task.last_execution)}</div>
                              <StatusBadge
                                status={task.last_status === 'success' ? 'success' : task.last_status === 'error' ? 'error' : 'warning'}
                              />
                            </div>
                          ) : (
                            'Never'
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            onClick={() => handleToggle(task.id)}
                            className="text-blue-600 hover:text-blue-900 mr-3"
                          >
                            {task.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button
                            onClick={() => handleEdit(task)}
                            className="text-indigo-600 hover:text-indigo-900 mr-3"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleExecute(task.id)}
                            disabled={executingTasks[task.id] !== undefined}
                            className={`mr-3 ${
                              executingTasks[task.id] !== undefined
                                ? 'text-gray-400 cursor-not-allowed'
                                : 'text-green-600 hover:text-green-900'
                            }`}
                          >
                            {executingTasks[task.id] !== undefined ? (
                              <span className="flex items-center">
                                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Executing...
                              </span>
                            ) : (
                              'Execute'
                            )}
                          </button>
                          <button
                            onClick={() => handleDelete(task.id)}
                            className="text-red-600 hover:text-red-900"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Planner;
