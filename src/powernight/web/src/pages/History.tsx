import React, { useState, useEffect, useRef } from 'react';
import { TaskExecutionLog, TaskExecutionLogsResponse } from '../types';
import { api } from '../utils/api';
import LogsTable from '../components/LogsTable';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBoundary from '../components/ErrorBoundary';

type StatusFilter = 'all' | 'success' | 'error';

const LIMIT = 100;
const TASK_NAME_DEBOUNCE_MS = 300;

const History: React.FC = () => {
  // Task execution logs state
  const [logs, setLogs] = useState<TaskExecutionLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Filter state (both filters are supported server-side by
  // GET /api/v1/logs/executions: status and task_name)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [taskNameFilter, setTaskNameFilter] = useState('');

  // Ignore responses from superseded requests (e.g. while typing in the
  // task name filter) so a slow response cannot clobber newer results.
  const requestIdRef = useRef(0);

  const loadLogs = async (resetOffset = false) => {
    const requestId = ++requestIdRef.current;

    try {
      setIsLoading(true);
      setError(null);

      // Derive the offset from the already-loaded logs at request time
      const currentOffset = resetOffset ? 0 : logs.length;
      const trimmedTaskName = taskNameFilter.trim();

      const response: TaskExecutionLogsResponse = await api.getTaskExecutionLogs({
        limit: LIMIT,
        offset: currentOffset,
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
        ...(trimmedTaskName ? { task_name: trimmedTaskName } : {}),
      });

      if (requestId !== requestIdRef.current) return;

      const newLogs = Array.isArray(response.logs) ? response.logs : [];

      if (resetOffset) {
        setLogs(newLogs);
      } else {
        setLogs(prev => [...prev, ...newLogs]);
      }

      setTotal(response.total || 0);
      setHasMore(response.has_more || false);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;

      console.error('[History] Error loading history:', err);
      setError(err instanceof Error ? err.message : 'Failed to load history');
      // Set empty state on error
      setLogs([]);
      setTotal(0);
      setHasMore(false);
    } finally {
      if (requestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  };

  const handleLoadMore = () => {
    if (!isLoading && hasMore) {
      loadLogs(false);
    }
  };

  // Initial load and reload when filters change (task name is debounced)
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      loadLogs(true);
    }, taskNameFilter ? TASK_NAME_DEBOUNCE_MS : 0);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, taskNameFilter]);

  return (
    <ErrorBoundary>
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
            <div className="mb-8">
              <h1 className="text-3xl font-bold text-gray-900">Task Executions</h1>
              <p className="mt-2 text-gray-600">
                View and manage task execution history
              </p>
            </div>

            {/* Filter Bar */}
            <div className="mb-4 bg-white p-4 rounded-lg shadow-sm border border-gray-200">
              <div className="flex flex-wrap gap-4 items-end">
                <div>
                  <label htmlFor="status-filter" className="block text-sm font-medium text-gray-700 mb-1">
                    Status
                  </label>
                  <select
                    id="status-filter"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
                    className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="all">All</option>
                    <option value="success">Success</option>
                    <option value="error">Error</option>
                  </select>
                </div>
                <div className="flex-1 min-w-[200px]">
                  <label htmlFor="task-name-filter" className="block text-sm font-medium text-gray-700 mb-1">
                    Task Name
                  </label>
                  <input
                    type="text"
                    id="task-name-filter"
                    value={taskNameFilter}
                    onChange={(e) => setTaskNameFilter(e.target.value)}
                    placeholder="Filter by task name..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                {(statusFilter !== 'all' || taskNameFilter) && (
                  <button
                    onClick={() => {
                      setStatusFilter('all');
                      setTaskNameFilter('');
                    }}
                    className="px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    Clear Filters
                  </button>
                )}
              </div>
            </div>

            {/* Results Summary */}
            <div className="mb-4">
              <p className="text-sm text-gray-600">
                Showing {logs.length} of {total} executions
              </p>
            </div>

            {/* Error Display */}
            {error && (
              <div className="mb-6 bg-red-50 border border-red-200 rounded-md p-4">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-red-800">Error</h3>
                    <div className="mt-2 text-sm text-red-700">
                      <p>{error}</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Task Execution Logs Table */}
            <LogsTable
              logs={logs}
              isLoading={isLoading}
            />

            {/* Load More Button */}
            {hasMore && !isLoading && (
              <div className="mt-6 text-center">
                <button
                  onClick={handleLoadMore}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  Load More History
                </button>
              </div>
            )}

            {/* Loading indicator for load more */}
            {isLoading && logs.length > 0 && (
              <div className="mt-6 text-center">
                <LoadingSpinner size="sm" />
                <span className="ml-2 text-gray-600">Loading more history...</span>
              </div>
            )}
        </div>
      </main>
    </div>
    </ErrorBoundary>
  );
};

export default History;
