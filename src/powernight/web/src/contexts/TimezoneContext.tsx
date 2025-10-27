import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import api from '../utils/api';

interface TimezoneInfo {
  timezone: string;
  offset: string;
  name: string;
  current_time: string | null;
}

interface TimezoneContextType {
  timezoneInfo: TimezoneInfo | null;
  currentTime: string;
  isLoading: boolean;
  error: string | null;
  refreshTimezone: () => Promise<void>;
  updateCurrentTime: () => void;
}

const TimezoneContext = createContext<TimezoneContextType | undefined>(undefined);

interface TimezoneProviderProps {
  children: ReactNode;
}

export const TimezoneProvider: React.FC<TimezoneProviderProps> = ({ children }) => {
  const [timezoneInfo, setTimezoneInfo] = useState<TimezoneInfo | null>(null);
  const [currentTime, setCurrentTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const updateCurrentTime = () => {
    if (!timezoneInfo?.timezone) return;

    try {
      const now = new Date();
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: timezoneInfo.timezone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      });
      
      // Format as yyyy-MM-dd HH:mm:ss
      const parts = formatter.formatToParts(now);
      const year = parts.find(part => part.type === 'year')?.value;
      const month = parts.find(part => part.type === 'month')?.value;
      const day = parts.find(part => part.type === 'day')?.value;
      const hour = parts.find(part => part.type === 'hour')?.value;
      const minute = parts.find(part => part.type === 'minute')?.value;
      const second = parts.find(part => part.type === 'second')?.value;
      
      if (year && month && day && hour && minute && second) {
        setCurrentTime(`${year}-${month}-${day} ${hour}:${minute}:${second}`);
      }
    } catch (err) {
      console.error('Failed to format current time:', err);
      setCurrentTime('Invalid timezone');
    }
  };

  const refreshTimezone = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      const data = await api.getTimezone();
      setTimezoneInfo(data);
      
      // Update current time immediately
      updateCurrentTime();
      
    } catch (err) {
      console.error('Failed to fetch timezone info:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch timezone info');
    } finally {
      setIsLoading(false);
    }
  };

  // Load timezone info on mount
  useEffect(() => {
    refreshTimezone();
  }, []);

  // Update current time every second
  useEffect(() => {
    if (!timezoneInfo?.timezone) return;

    const interval = setInterval(updateCurrentTime, 1000);
    return () => clearInterval(interval);
  }, [timezoneInfo?.timezone]);

  const contextValue: TimezoneContextType = {
    timezoneInfo,
    currentTime,
    isLoading,
    error,
    refreshTimezone,
    updateCurrentTime,
  };

  return (
    <TimezoneContext.Provider value={contextValue}>
      {children}
    </TimezoneContext.Provider>
  );
};

export const useTimezone = (): TimezoneContextType => {
  const context = useContext(TimezoneContext);
  if (context === undefined) {
    throw new Error('useTimezone must be used within a TimezoneProvider');
  }
  return context;
};
