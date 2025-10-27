/**
 * Centralized datetime formatting utilities for PowerNight.
 * 
 * All datetime formatting should use these functions to ensure consistency
 * across the application. The backend already provides timezone-aware
 * timestamps, so this formatter primarily handles display formatting.
 */

/**
 * Format a datetime string or Date object to the standard display format.
 * 
 * Format: "yyyy-MM-dd HH:mm:ss"
 * 
 * @param dateString - ISO datetime string or Date object
 * @returns Formatted datetime string or 'Invalid Date' for invalid inputs
 */
export const formatDateTime = (dateString: string | Date | null | undefined): string => {
  if (!dateString) {
    return 'Never';
  }

  try {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }

    // Format as yyyy-MM-dd HH:mm:ss
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');

    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  } catch (error) {
    console.error('Date formatting error:', error);
    return 'Invalid Date';
  }
};

/**
 * Format a datetime string or Date object with timezone abbreviation.
 * 
 * Format: "yyyy-MM-dd HH:mm:ss (TZ)"
 * 
 * @param dateString - ISO datetime string or Date object
 * @param timezone - Timezone string (e.g., 'Europe/Berlin')
 * @returns Formatted datetime string with timezone abbreviation
 */
export const formatDateTimeWithTimezone = (
  dateString: string | Date | null | undefined,
  timezone?: string
): string => {
  if (!dateString) {
    return 'Never';
  }

  try {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }

    // Use Intl.DateTimeFormat for timezone-aware formatting
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZoneName: 'short'
    });

    const parts = formatter.formatToParts(date);
    const year = parts.find(part => part.type === 'year')?.value;
    const month = parts.find(part => part.type === 'month')?.value;
    const day = parts.find(part => part.type === 'day')?.value;
    const hour = parts.find(part => part.type === 'hour')?.value;
    const minute = parts.find(part => part.type === 'minute')?.value;
    const second = parts.find(part => part.type === 'second')?.value;
    const timeZoneName = parts.find(part => part.type === 'timeZoneName')?.value;

    if (year && month && day && hour && minute && second) {
      const formattedDate = `${year}-${month}-${day} ${hour}:${minute}:${second}`;
      return timeZoneName ? `${formattedDate} (${timeZoneName})` : formattedDate;
    }

    return 'Invalid Date';
  } catch (error) {
    console.error('Date formatting error:', error);
    return 'Invalid Date';
  }
};

/**
 * Format a datetime string or Date object to a relative time string.
 * 
 * @param dateString - ISO datetime string or Date object
 * @returns Relative time string (e.g., "2h ago", "3d ago")
 */
export const formatRelativeTime = (dateString: string | Date | null | undefined): string => {
  if (!dateString) {
    return 'Never';
  }

  try {
    const date = typeof dateString === 'string' ? new Date(dateString) : dateString;
    
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    
    const now = new Date();
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    if (diffInSeconds < 60) {
      return `${diffInSeconds}s ago`;
    } else if (diffInSeconds < 3600) {
      const minutes = Math.floor(diffInSeconds / 60);
      return `${minutes}m ago`;
    } else if (diffInSeconds < 86400) {
      const hours = Math.floor(diffInSeconds / 3600);
      return `${hours}h ago`;
    } else {
      const days = Math.floor(diffInSeconds / 86400);
      return `${days}d ago`;
    }
  } catch (error) {
    console.error('Relative time formatting error:', error);
    return 'Invalid Date';
  }
};

/**
 * Get the current time in the specified timezone.
 * 
 * @param timezone - Timezone string (e.g., 'Europe/Berlin')
 * @returns Current time formatted as "yyyy-MM-dd HH:mm:ss"
 */
export const getCurrentTime = (timezone?: string): string => {
  try {
    const now = new Date();
    
    if (timezone) {
      return formatDateTimeWithTimezone(now, timezone).replace(/ \([^)]+\)$/, '');
    }
    
    return formatDateTime(now);
  } catch (error) {
    console.error('Current time formatting error:', error);
    return 'Invalid Date';
  }
};

/**
 * Get the current time with timezone abbreviation.
 * 
 * @param timezone - Timezone string (e.g., 'Europe/Berlin')
 * @returns Current time formatted as "yyyy-MM-dd HH:mm:ss (TZ)"
 */
export const getCurrentTimeWithTimezone = (timezone?: string): string => {
  try {
    const now = new Date();
    return formatDateTimeWithTimezone(now, timezone);
  } catch (error) {
    console.error('Current time formatting error:', error);
    return 'Invalid Date';
  }
};
