import React, { useState, useMemo } from 'react';
import { TaskExecutionLog } from '../types';
import Tooltip from './Tooltip';
import { formatDate } from '../utils/helpers';

interface LogsTableProps {
  logs: TaskExecutionLog[];
  isLoading?: boolean;
}

type SortField = 'started_at' | 'task_name' | 'execution_type' | 'command' | 'status';
type SortDirection = 'asc' | 'desc';

const LogsTable: React.FC<LogsTableProps> = ({ logs, isLoading = false }) => {
  const [sortField, setSortField] = useState<SortField>('started_at');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const formatDateTime = (dateString: string) => {
    return formatDate(dateString);
  };

  const formatCommandParams = (params: Record<string, any>) => {
    if (!params || Object.keys(params).length === 0) {
      return 'None';
    }
    return JSON.stringify(params, null, 2);
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium';
    
    switch (status) {
      case 'success':
        return `${baseClasses} bg-green-100 text-green-800`;
      case 'error':
        return `${baseClasses} bg-red-100 text-red-800`;
      case 'running':
        return `${baseClasses} bg-blue-100 text-blue-800`;
      case 'pending':
        return `${baseClasses} bg-yellow-100 text-yellow-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  const getExecutionTypeBadge = (type: string) => {
    const baseClasses = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium';
    
    switch (type) {
      case 'scheduled':
        return `${baseClasses} bg-purple-100 text-purple-800`;
      case 'manual':
        return `${baseClasses} bg-indigo-100 text-indigo-800`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800`;
    }
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedLogs = useMemo(() => {
    return [...logs].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      switch (sortField) {
        case 'started_at':
          aValue = new Date(a.started_at).getTime();
          bValue = new Date(b.started_at).getTime();
          break;
        case 'task_name':
          aValue = a.task_name?.toLowerCase() || '';
          bValue = b.task_name?.toLowerCase() || '';
          break;
        case 'execution_type':
          aValue = a.execution_type;
          bValue = b.execution_type;
          break;
        case 'command':
          aValue = a.command;
          bValue = b.command;
          break;
        case 'status':
          aValue = a.status;
          bValue = b.status;
          break;
        default:
          return 0;
      }

      if (aValue < bValue) return sortDirection === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [logs, sortField, sortDirection]);

  const SortButton: React.FC<{ field: SortField; children: React.ReactNode }> = ({ field, children }) => (
    <button
      onClick={() => handleSort(field)}
      className="flex items-center space-x-1 text-left font-medium text-gray-900 hover:text-gray-700 focus:outline-none"
    >
      <span>{children}</span>
      {sortField === field && (
        <span className="text-gray-400">
          {sortDirection === 'asc' ? '↑' : '↓'}
        </span>
      )}
    </button>
  );

  if (isLoading && logs.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg">
        <div className="flex justify-center items-center py-12" data-testid="logs-loading">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-600">Loading logs...</span>
        </div>
      </div>
    );
  }

  if (!isLoading && logs.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg" data-testid="logs-empty">
        <div className="text-center py-12">
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <h3 className="mt-2 text-lg font-medium text-gray-900">No execution logs found</h3>
          <p className="mt-1 text-gray-500">Task executions will appear here once tasks are run.</p>
          <div className="mt-6">
            <p className="text-sm text-gray-400">
              To create logs, go to the <a href="/scheduling" className="text-blue-600 hover:text-blue-500">Planner</a> page and execute a task.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white shadow overflow-hidden sm:rounded-md">
      <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
        <div>
          <h3 className="text-lg leading-6 font-medium text-gray-900">
            Task Execution Logs
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-gray-500">
            History of all Task Executions
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <SortButton field="started_at">Timestamp</SortButton>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <SortButton field="task_name">Task Name</SortButton>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <SortButton field="execution_type">Type</SortButton>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <SortButton field="command">Command</SortButton>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <span className="text-gray-900">Parameters</span>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <span className="text-gray-900">API Response</span>
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <SortButton field="status">Status</SortButton>
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {sortedLogs.map((log) => {
              const timestamp = formatDateTime(log.started_at);
              const commandParams = formatCommandParams(log.command_params);
              const apiResponse = log.api_response ? JSON.stringify(log.api_response, null, 2) : 'No response';

              return (
                <tr key={log.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 font-mono">
                    {timestamp}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {log.task_name || 'Unknown'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={getExecutionTypeBadge(log.execution_type)}>
                      {log.execution_type.charAt(0).toUpperCase() + log.execution_type.slice(1)}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {log.command}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 max-w-xs min-w-[120px]">
                    <Tooltip content={<pre className="whitespace-pre-wrap">{commandParams}</pre>}>
                      <div className="truncate cursor-help">
                        {commandParams.length > 50 ? `${commandParams.substring(0, 50)}...` : commandParams}
                      </div>
                    </Tooltip>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-900 max-w-xs min-w-[120px]">
                    <Tooltip content={<pre className="whitespace-pre-wrap">{apiResponse}</pre>}>
                      <div className="truncate cursor-help">
                        {apiResponse.length > 50 ? `${apiResponse.substring(0, 50)}...` : apiResponse}
                      </div>
                    </Tooltip>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={getStatusBadge(log.status)}>
                      {log.status.charAt(0).toUpperCase() + log.status.slice(1)}
                    </span>
                    {log.error_message && (
                      <Tooltip content={log.error_message}>
                        <span className="ml-1 text-red-500 cursor-help">⚠️</span>
                      </Tooltip>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default LogsTable;
