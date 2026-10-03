import { format, parseISO, isValid } from 'date-fns';
import { formatDateTime, formatRelativeTime as formatRelativeTimeImpl } from './dateTimeFormatter';

// Date formatting utilities
export const formatDate = (date: string | Date, formatString: string = 'yyyy-MM-dd HH:mm:ss'): string => {
  // Use the new centralized formatter for the default format
  if (formatString === 'yyyy-MM-dd HH:mm:ss') {
    return formatDateTime(date);
  }
  
  // Fallback to date-fns for custom formats
  try {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    if (!isValid(dateObj)) {
      return 'Invalid Date';
    }
    return format(dateObj, formatString);
  } catch (error) {
    console.error('Date formatting error:', error);
    return 'Invalid Date';
  }
};

// Format time in 24-hour format
export const formatTime24 = (date: string | Date): string => {
  try {
    const dateObj = typeof date === 'string' ? parseISO(date) : date;
    if (!isValid(dateObj)) {
      return 'Invalid Date';
    }
    return format(dateObj, 'HH:mm');
  } catch (error) {
    console.error('Time formatting error:', error);
    return 'Invalid Date';
  }
};

export const formatRelativeTime = (date: string | Date): string => {
  // Delegates to the centralized formatter.
  return formatRelativeTimeImpl(date);
};

// Log level utilities
export const getLogLevelColor = (level: string): string => {
  switch (level.toUpperCase()) {
    case 'DEBUG':
      return 'text-gray-500';
    case 'INFO':
      return 'text-blue-600';
    case 'WARNING':
      return 'text-yellow-600';
    case 'ERROR':
      return 'text-red-600';
    case 'CRITICAL':
      return 'text-red-800 font-bold';
    default:
      return 'text-gray-700';
  }
};

export const getLogLevelBadgeColor = (level: string): string => {
  switch (level.toUpperCase()) {
    case 'DEBUG':
      return 'bg-gray-100 text-gray-800';
    case 'INFO':
      return 'bg-blue-100 text-blue-800';
    case 'WARNING':
      return 'bg-yellow-100 text-yellow-800';
    case 'ERROR':
      return 'bg-red-100 text-red-800';
    case 'CRITICAL':
      return 'bg-red-200 text-red-900 font-bold';
    default:
      return 'bg-gray-100 text-gray-800';
  }
};

// Status utilities
export const getStatusColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'healthy':
      return 'text-green-600';
    case 'degraded':
      return 'text-yellow-600';
    case 'unhealthy':
      return 'text-red-600';
    case 'success':
    case 'enabled':
      return 'text-green-600';
    case 'error':
      return 'text-red-600';
    case 'warning':
    case 'disabled':
      return 'text-yellow-600';
    default:
      return 'text-gray-600';
  }
};

export const getStatusBadgeColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'healthy':
      return 'bg-green-100 text-green-800';
    case 'degraded':
      return 'bg-yellow-100 text-yellow-800';
    case 'unhealthy':
      return 'bg-red-100 text-red-800';
    case 'success':
    case 'enabled':
      return 'bg-green-100 text-green-800';
    case 'error':
      return 'bg-red-100 text-red-800';
    case 'warning':
    case 'disabled':
      return 'bg-yellow-100 text-yellow-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
};

// Validation utilities
export const validatePercentage = (value: number): boolean => {
  return !isNaN(value) && value >= 0 && value <= 100;
};

export const validateIPAddress = (ip: string): boolean => {
  const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  return ipRegex.test(ip);
};

export const validateEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

export const validateTime = (time: string): boolean => {
  const timeRegex = /^([01]?[0-9]|2[0-3]):[0-5][0-9]$/;
  return timeRegex.test(time);
};

// String utilities
export const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength) + '...';
};

export const capitalizeFirst = (text: string): string => {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
};

export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// Array utilities
export const groupBy = <T>(array: T[], key: keyof T): Record<string, T[]> => {
  return array.reduce((groups, item) => {
    const group = String(item[key]);
    groups[group] = groups[group] || [];
    groups[group].push(item);
    return groups;
  }, {} as Record<string, T[]>);
};

export const sortBy = <T>(array: T[], key: keyof T, direction: 'asc' | 'desc' = 'asc'): T[] => {
  return [...array].sort((a, b) => {
    const aVal = a[key];
    const bVal = b[key];
    
    if (aVal < bVal) return direction === 'asc' ? -1 : 1;
    if (aVal > bVal) return direction === 'asc' ? 1 : -1;
    return 0;
  });
};

// Error handling utilities
export const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return 'An unknown error occurred';
};

export const isNetworkError = (error: unknown): boolean => {
  if (error instanceof Error) {
    return error.message.includes('Network Error') || 
           error.message.includes('Failed to fetch') ||
           error.message.includes('timeout');
  }
  return false;
};

// Local storage utilities
export const storage = {
  get: <T>(key: string, defaultValue?: T): T | null => {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue || null;
    } catch (error) {
      console.error('Error reading from localStorage:', error);
      return defaultValue || null;
    }
  },
  
  set: <T>(key: string, value: T): void => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error('Error writing to localStorage:', error);
    }
  },
  
  remove: (key: string): void => {
    try {
      localStorage.removeItem(key);
    } catch (error) {
      console.error('Error removing from localStorage:', error);
    }
  },
  
  clear: (): void => {
    try {
      localStorage.clear();
    } catch (error) {
      console.error('Error clearing localStorage:', error);
    }
  }
};

// Debounce utility
export const debounce = <T extends (...args: never[]) => unknown>(
  func: T,
  wait: number
): ((...args: Parameters<T>) => void) => {
  let timeout: NodeJS.Timeout;
  
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};

// Throttle utility
export const throttle = <T extends (...args: never[]) => unknown>(
  func: T,
  limit: number
): ((...args: Parameters<T>) => void) => {
  let inThrottle: boolean;
  
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
};

// Class name utility (similar to clsx)
export const cn = (...classes: (string | undefined | null | false)[]): string => {
  return classes.filter(Boolean).join(' ');
};
