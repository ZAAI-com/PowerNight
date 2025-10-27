import React, { useState, useEffect, useCallback, useRef } from 'react';
import { TaskExecutionLog, TaskExecutionLogsResponse } from '../types';
import { api } from '../utils/api';
import LogsTable from '../components/LogsTable';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBoundary from '../components/ErrorBoundary';


const History: React.FC = () => {
  // Task execution logs state
  const [logs, setLogs] = useState<TaskExecutionLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  // Use ref for offset to avoid re-render loops
  const offsetRef = useRef(0);
  const limit = 100;

  const loadLogs = useCallback(async (resetOffset = false) => {
    try {
      setIsLoading(true);
      setError(null);

      const currentOffset = resetOffset ? 0 : offsetRef.current;
      const filterParams: any = {
        limit,
        offset: currentOffset
      };


      console.log('[History] Fetching logs with params:', filterParams);

      const response: TaskExecutionLogsResponse = await api.getTaskExecutionLogs(filterParams);

      console.log('[History] Received response:', {
        logsCount: response.logs?.length || 0,
        total: response.total,
        hasMore: response.has_more
      });

      if (resetOffset) {
        setLogs(response.logs || []);
        offsetRef.current = 0;
      } else {
        setLogs(prev => [...prev, ...(response.logs || [])]);
        offsetRef.current = currentOffset + (response.logs?.length || 0);
      }

      setTotal(response.total || 0);
      setHasMore(response.has_more || false);
    } catch (err) {
      console.error('[History] Error loading history:', err);
      setError(err instanceof Error ? err.message : 'Failed to load history');
      // Set empty state on error
      setLogs([]);
      setTotal(0);
      setHasMore(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleLoadMore = () => {
    if (!isLoading && hasMore) {
      loadLogs(false);
    }
  };

  useEffect(() => {
    console.log('[History] Component mounted, loading initial logs...');
    loadLogs(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
