// PowerNight TypeScript Types

export interface AuthStatus {
  authenticated: boolean;
  email?: string;
  site_name?: string;
  site_id?: string;
  energy_site_id?: string;
  token_expired?: boolean;
  expires_at?: string;
}

export interface PowerwallStatus {
  connected: boolean;
  backup_reserve_percentage: number;
  last_communication?: string;
  error?: string;
  powerwall_name?: string;
}

export interface SystemStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  powerwall: PowerwallStatus;
  automation: {
    enabled: boolean;
    next_action?: string;
    next_action_time?: string;
  };
  configuration: {
    loaded: boolean;
    automation_enabled: boolean;
    powerwall_configured: boolean;
  };
}

export interface BackupReserveData {
  backup_reserve_percentage: number;
  connected: boolean;
  demo_mode?: boolean;
  powerwall_name?: string;
  last_communication?: string;
  error?: string;
}

export type CommandType = 'mode' | 'reserve' | 'current' | 'gridcharging' | 'gridexport';

export interface Task {
  id: string;
  name: string;
  time: string;
  command: CommandType;
  command_params: Record<string, unknown>;
  enabled: boolean;
  last_execution?: string;
  last_status?: 'success' | 'error' | 'pending';
  last_error?: string;
  execution_count: number;
  created_at?: string;
  updated_at?: string;
  is_registered?: boolean;
}

export interface CommandDefinition {
  description: string;
  params: Record<string, ParamDefinition>;
}

export interface ParamDefinition {
  type: 'string' | 'number' | 'boolean';
  required: boolean;
  options?: string[];
  min?: number;
  max?: number;
  unit?: string;
}

export interface TaskPreset {
  id: string;
  name: string;
  command: CommandType;
  command_params: Record<string, unknown>;
  default_time?: string;
  is_builtin: boolean;
  sort_order: number;
  created_at?: string;
  updated_at?: string;
}

export interface TaskFormData {
  name: string;
  time: string;
  command: CommandType;
  command_params: Record<string, unknown>;
  enabled: boolean;
}

export interface TaskExecution {
  id: string;
  task_id: string;
  status: 'pending' | 'running' | 'success' | 'error';
  started_at: string;
  completed_at?: string;
  result?: unknown;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface TaskExecutionLog {
  id: string;
  task_id: string;
  task_name: string;
  execution_type: 'scheduled' | 'manual';
  command: string;
  command_params: Record<string, unknown>;
  api_response: unknown;
  status: 'pending' | 'running' | 'success' | 'error';
  started_at: string;
  completed_at?: string;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface TaskExecutionLogsResponse {
  logs: TaskExecutionLog[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface LogEntry {
  id?: string;
  timestamp: string;
  level: string;
  message: string;
  component?: string;
  operation?: string;
  duration_ms?: number;
  user_id?: string;
  session_id?: string;
  request_id?: string;
  error_details?: string;
  metadata?: Record<string, unknown>;
  api_response?: Record<string, unknown>;
  response_size_bytes?: number;
}

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
  timestamp: string;
  request_id?: string;
}

export interface ApiError {
  success: false;
  error: string;
  message: string;
  timestamp: string;
  request_id?: string;
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  version: string;
  uptime_seconds: number;
  configuration: {
    loaded: boolean;
    automation_enabled: boolean;
    powerwall_configured: boolean;
  };
  issues?: string[];
}

export interface Metrics {
  powerwall_requests: number;
  powerwall_errors: number;
  automation_executions: number;
  automation_errors: number;
  uptime_seconds: number;
  last_updated: string;
}

// Form types
export interface ReserveFormData {
  percentage: number;
  reason: string;
}

// UI State types
export interface LoadingState {
  isLoading: boolean;
  error?: string;
  message?: string;
}

export interface PaginationState {
  page: number;
  limit: number;
  total: number;
  hasMore: boolean;
}

export interface FilterState {
  level?: string;
  component?: string;
  startDate?: string;
  endDate?: string;
}

// Event types
export interface PowerNightEvent {
  type: 'status-update' | 'auth-required' | 'connection-error' | 'api-error';
  detail?: unknown;
}

export interface StatusUpdateEvent extends PowerNightEvent {
  type: 'status-update';
  detail: {
    status: SystemStatus;
  };
}

export interface AuthRequiredEvent extends PowerNightEvent {
  type: 'auth-required';
}

export interface ConnectionErrorEvent extends PowerNightEvent {
  type: 'connection-error';
  detail: Error;
}

export interface ApiErrorEvent extends PowerNightEvent {
  type: 'api-error';
  detail: {
    error: Error;
    context: string;
  };
}
