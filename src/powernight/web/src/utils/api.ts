import axios, { AxiosInstance, AxiosResponse, AxiosError } from 'axios';
import {
  ApiResponse,
  SystemStatus,
  BackupReserveData,
  HealthStatus,
  Metrics,
  ReserveFormData,
  Task,
  TaskFormData,
  TaskExecution,
  TaskExecutionLogsResponse,
  CommandDefinition,
  TaskPreset
} from '../types';

class PowerNightAPI {
  private client: AxiosInstance;
  private apiKey: string | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: '/api/v1',
      timeout: 90000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
    this.loadApiKey();
  }

  private setupInterceptors() {
    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Only add authentication if we have an API key
        // For demo mode, authentication might be disabled on the server
        if (this.apiKey) {
          config.headers['X-API-Key'] = this.apiKey;
        }

        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          this.clearApiKey();
          window.dispatchEvent(new CustomEvent('powernight:auth-required'));
        } else if (error.code === 'NETWORK_ERROR' || error.message.includes('Network Error')) {
          window.dispatchEvent(new CustomEvent('powernight:connection-error', { 
            detail: error 
          }));
        } else {
          window.dispatchEvent(new CustomEvent('powernight:api-error', { 
            detail: { error, context: 'API Request' } 
          }));
        }
        return Promise.reject(error);
      }
    );
  }

  // API Key management
  private loadApiKey() {
    this.apiKey = localStorage.getItem('powernight_api_key');
  }

  setApiKey(key: string) {
    this.apiKey = key;
    localStorage.setItem('powernight_api_key', key);
  }

  clearApiKey() {
    this.apiKey = null;
    localStorage.removeItem('powernight_api_key');
  }

  isAuthenticated(): boolean {
    // If we have an API key, we're authenticated
    if (this.apiKey) {
      return true;
    }
    
    // If no API key, check if the server requires authentication
    // by making a test request to the health endpoint
    // This is a simple way to detect if auth is required
    return false;
  }

  async checkAuthRequired(): Promise<boolean> {
    try {
      // Try to access a protected endpoint without authentication
      const response = await fetch('/api/v1/auth/check', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      // If we get a 401, authentication is required
      return response.status === 401;
    } catch {
      // If there's an error, assume auth is required for safety
      return true;
    }
  }

  async authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (this.apiKey) {
      headers.set('X-API-Key', this.apiKey);
    }

    try {
      const response = await fetch(input, { ...init, headers });
      if (response.status === 401) {
        this.clearApiKey();
        window.dispatchEvent(new CustomEvent('powernight:auth-required'));
      }
      return response;
    } catch (error) {
      window.dispatchEvent(new CustomEvent('powernight:connection-error', {
        detail: error,
      }));
      throw error;
    }
  }


  // Health and status endpoints
  async getHealth(): Promise<HealthStatus> {
    const response = await this.client.get<HealthStatus>('/health');
    return response.data;
  }

  async getStatus(): Promise<SystemStatus> {
    const response = await this.client.get<ApiResponse<SystemStatus>>('/status');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get status');
    }
    return response.data.data!;
  }

  // Powerwall endpoints
  async getPowerwallStatus(): Promise<BackupReserveData> {
    const response = await this.client.get<ApiResponse<BackupReserveData>>('/backup-reserve');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get Powerwall status');
    }
    return response.data.data!;
  }

  async setPowerwallReserve(data: ReserveFormData): Promise<BackupReserveData> {
    const response = await this.client.post<ApiResponse<BackupReserveData>>('/backup-reserve', {
      percentage: data.percentage,
      reason: data.reason || 'Manual control via web interface'
    });
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to set backup reserve');
    }
    return response.data.data!;
  }

  async testPowerwallConnection(): Promise<ApiResponse> {
    const response = await this.client.post<ApiResponse>('/test-connection');
    return response.data;
  }


  // Metrics endpoints
  async getMetrics(): Promise<Metrics> {
    const response = await this.client.get<ApiResponse<Metrics>>('/metrics');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get metrics');
    }
    return response.data.data!;
  }

  // Task endpoints
  async getTasks(enabledOnly?: boolean): Promise<{ tasks: Task[]; total: number }> {
    const params = enabledOnly ? `?enabled_only=${enabledOnly}` : '';
    const response = await this.client.get<ApiResponse<{ tasks: Task[]; total: number }>>(`/tasks${params}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get tasks');
    }
    return { tasks: response.data.data!.tasks, total: response.data.data!.total };
  }

  async getTask(id: string): Promise<Task> {
    const response = await this.client.get<ApiResponse<Task>>(`/tasks/${id}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get task');
    }
    return response.data.data!;
  }

  async createTask(task: TaskFormData): Promise<Task> {
    const response = await this.client.post<ApiResponse<Task>>('/tasks', task);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to create task');
    }
    return response.data.data!;
  }

  async updateTask(id: string, task: Partial<TaskFormData>): Promise<Task> {
    const response = await this.client.put<ApiResponse<Task>>(`/tasks/${id}`, task);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to update task');
    }
    return response.data.data!;
  }

  async deleteTask(id: string): Promise<void> {
    const response = await this.client.delete<ApiResponse>(`/tasks/${id}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to delete task');
    }
  }

  async toggleTask(id: string): Promise<Task> {
    const response = await this.client.post<ApiResponse<Task>>(`/tasks/${id}/toggle`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to toggle task');
    }
    return response.data.data!;
  }

  async executeTask(id: string): Promise<{ execution_id: string; task_id: string; status: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ execution_id: string; task_id: string; status: string; message: string }>>(`/tasks/${id}/execute`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to execute task');
    }
    return response.data.data!;
  }

  async reloadAllTasks(): Promise<{ old_task_count: number; new_task_count: number; timezone: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ old_task_count: number; new_task_count: number; timezone: string; message: string }>>('/tasks/reload');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to reload tasks');
    }
    return response.data.data!;
  }

  async getTaskCommands(): Promise<{ commands: Record<string, CommandDefinition> }> {
    const response = await this.client.get<ApiResponse<{ commands: Record<string, CommandDefinition> }>>('/tasks/commands');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get task commands');
    }
    return response.data.data!;
  }

  async getTaskExecution(taskId: string, executionId: string): Promise<TaskExecution> {
    const response = await this.client.get<ApiResponse<TaskExecution>>(`/tasks/${taskId}/executions/${executionId}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get task execution');
    }
    return response.data.data!;
  }

  async getTaskExecutions(taskId: string, limit: number = 10): Promise<{ executions: TaskExecution[]; total: number }> {
    const response = await this.client.get<ApiResponse<{ executions: TaskExecution[]; total: number }>>(`/tasks/${taskId}/executions?limit=${limit}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get task executions');
    }
    return response.data.data!;
  }

  // Task Preset endpoints
  async getTaskPresets(): Promise<{ presets: TaskPreset[]; total: number }> {
    const response = await this.client.get<ApiResponse<{ presets: TaskPreset[]; total: number }>>('/tasks/presets');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get presets');
    }
    return response.data.data!;
  }

  async createTaskPreset(preset: {
    name: string;
    command: CommandType;
    command_params: Record<string, unknown>;
    default_time?: string;
  }): Promise<TaskPreset> {
    const response = await this.client.post<ApiResponse<TaskPreset>>('/tasks/presets', preset);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to create preset');
    }
    return response.data.data!;
  }

  async deleteTaskPreset(id: string): Promise<void> {
    const response = await this.client.delete<ApiResponse>(`/tasks/presets/${id}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to delete preset');
    }
  }

  // Task Execution Logs endpoints
  async getTaskExecutionLogs(filters?: {
    limit?: number;
    offset?: number;
    task_name?: string;
    execution_type?: 'scheduled' | 'manual';
    status?: 'pending' | 'running' | 'success' | 'error';
    start_date?: string;
    end_date?: string;
  }): Promise<TaskExecutionLogsResponse> {
    const params = new URLSearchParams();

    if (filters?.limit) params.append('limit', filters.limit.toString());
    if (filters?.offset) params.append('offset', filters.offset.toString());
    if (filters?.task_name) params.append('task_name', filters.task_name);
    if (filters?.execution_type) params.append('execution_type', filters.execution_type);
    if (filters?.status) params.append('status', filters.status);
    if (filters?.start_date) params.append('start_date', filters.start_date);
    if (filters?.end_date) params.append('end_date', filters.end_date);

    const response = await this.client.get<ApiResponse<TaskExecutionLogsResponse>>(`/logs/executions?${params.toString()}`);
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get task execution logs');
    }
    return response.data.data!;
  }

  // Authentication
  async authenticate(apiKey: string): Promise<boolean> {
    const tempApiKey = this.apiKey;
    this.apiKey = apiKey;
    
    try {
      await this.client.get('/auth/check');
      this.setApiKey(apiKey);
      return true;
    } catch (error) {
      // Restore previous API key on failure
      this.apiKey = tempApiKey;
      throw error;
    }
  }

  async logout(): Promise<void> {
    this.clearApiKey();
  }

  // Utility methods
  async ping(): Promise<boolean> {
    try {
      await this.getHealth();
      return true;
    } catch {
      return false;
    }
  }

  // Real-time updates (polling)
  private pollingInterval: NodeJS.Timeout | null = null;

  startPolling(interval: number = 30000) {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }

    this.pollingInterval = setInterval(async () => {
      try {
        const status = await this.getStatus();
        window.dispatchEvent(new CustomEvent('powernight:status-update', {
          detail: { status }
        }));
      } catch (error) {
        console.warn('Polling update failed:', error);
      }
    }, interval);
  }

  stopPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }

  // Timezone configuration endpoints
  async getTimezone(): Promise<{ timezone: string; offset: string; name: string; current_time: string | null }> {
    const response = await this.client.get<ApiResponse<{ timezone: string; offset: string; name: string; current_time: string | null }>>('/config/timezone');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get timezone');
    }
    return response.data.data!;
  }

  async updateTimezone(timezone: string): Promise<{ timezone: string; message: string }> {
    const response = await this.client.post<ApiResponse<{ timezone: string; message: string }>>('/config/timezone', { timezone });
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to update timezone');
    }
    return response.data.data!;
  }

  async getAvailableTimezones(): Promise<{ timezones: Array<{ value: string; label: string; region: string; offset: string }>; count: number }> {
    const response = await this.client.get<ApiResponse<{ timezones: Array<{ value: string; label: string; region: string; offset: string }>; count: number }>>('/config/timezones');
    if (!response.data.success) {
      throw new Error(response.data.error || 'Failed to get timezones');
    }
    return response.data.data!;
  }
}

// Create and export singleton instance
export const api = new PowerNightAPI();
export default api;
