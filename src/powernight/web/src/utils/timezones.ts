/**
 * Timezone utilities for PowerNight
 *
 * This file contains common timezones organized by region for easy selection.
 * The full list is fetched from the API which includes all pytz timezones.
 */

export interface Timezone {
  value: string;
  label: string;
  region: string;
  offset?: string;
}

/**
 * Common European timezones (most commonly used)
 */
export const COMMON_EUROPEAN_TIMEZONES: Timezone[] = [
  { value: 'Europe/Berlin', label: 'Europe/Berlin (Germany)', region: 'Europe' },
  { value: 'Europe/London', label: 'Europe/London (UK)', region: 'Europe' },
  { value: 'Europe/Paris', label: 'Europe/Paris (France)', region: 'Europe' },
  { value: 'Europe/Madrid', label: 'Europe/Madrid (Spain)', region: 'Europe' },
  { value: 'Europe/Rome', label: 'Europe/Rome (Italy)', region: 'Europe' },
  { value: 'Europe/Amsterdam', label: 'Europe/Amsterdam (Netherlands)', region: 'Europe' },
  { value: 'Europe/Brussels', label: 'Europe/Brussels (Belgium)', region: 'Europe' },
  { value: 'Europe/Vienna', label: 'Europe/Vienna (Austria)', region: 'Europe' },
  { value: 'Europe/Zurich', label: 'Europe/Zurich (Switzerland)', region: 'Europe' },
  { value: 'Europe/Stockholm', label: 'Europe/Stockholm (Sweden)', region: 'Europe' },
  { value: 'Europe/Copenhagen', label: 'Europe/Copenhagen (Denmark)', region: 'Europe' },
  { value: 'Europe/Oslo', label: 'Europe/Oslo (Norway)', region: 'Europe' },
  { value: 'Europe/Helsinki', label: 'Europe/Helsinki (Finland)', region: 'Europe' },
  { value: 'Europe/Warsaw', label: 'Europe/Warsaw (Poland)', region: 'Europe' },
  { value: 'Europe/Prague', label: 'Europe/Prague (Czech Republic)', region: 'Europe' },
  { value: 'Europe/Budapest', label: 'Europe/Budapest (Hungary)', region: 'Europe' },
  { value: 'Europe/Athens', label: 'Europe/Athens (Greece)', region: 'Europe' },
  { value: 'Europe/Dublin', label: 'Europe/Dublin (Ireland)', region: 'Europe' },
  { value: 'Europe/Lisbon', label: 'Europe/Lisbon (Portugal)', region: 'Europe' },
  { value: 'Europe/Moscow', label: 'Europe/Moscow (Russia)', region: 'Europe' },
];

/**
 * Common timezones from other regions
 */
export const COMMON_TIMEZONES: Timezone[] = [
  // Americas
  { value: 'America/New_York', label: 'America/New_York (US Eastern)', region: 'America' },
  { value: 'America/Chicago', label: 'America/Chicago (US Central)', region: 'America' },
  { value: 'America/Denver', label: 'America/Denver (US Mountain)', region: 'America' },
  { value: 'America/Los_Angeles', label: 'America/Los_Angeles (US Pacific)', region: 'America' },
  { value: 'America/Toronto', label: 'America/Toronto (Canada)', region: 'America' },
  { value: 'America/Mexico_City', label: 'America/Mexico_City (Mexico)', region: 'America' },
  { value: 'America/Sao_Paulo', label: 'America/Sao_Paulo (Brazil)', region: 'America' },
  { value: 'America/Buenos_Aires', label: 'America/Buenos_Aires (Argentina)', region: 'America' },

  // Asia
  { value: 'Asia/Tokyo', label: 'Asia/Tokyo (Japan)', region: 'Asia' },
  { value: 'Asia/Shanghai', label: 'Asia/Shanghai (China)', region: 'Asia' },
  { value: 'Asia/Hong_Kong', label: 'Asia/Hong_Kong', region: 'Asia' },
  { value: 'Asia/Singapore', label: 'Asia/Singapore', region: 'Asia' },
  { value: 'Asia/Seoul', label: 'Asia/Seoul (South Korea)', region: 'Asia' },
  { value: 'Asia/Bangkok', label: 'Asia/Bangkok (Thailand)', region: 'Asia' },
  { value: 'Asia/Dubai', label: 'Asia/Dubai (UAE)', region: 'Asia' },
  { value: 'Asia/Kolkata', label: 'Asia/Kolkata (India)', region: 'Asia' },
  { value: 'Asia/Jakarta', label: 'Asia/Jakarta (Indonesia)', region: 'Asia' },

  // Pacific
  { value: 'Australia/Sydney', label: 'Australia/Sydney', region: 'Australia' },
  { value: 'Australia/Melbourne', label: 'Australia/Melbourne', region: 'Australia' },
  { value: 'Australia/Brisbane', label: 'Australia/Brisbane', region: 'Australia' },
  { value: 'Pacific/Auckland', label: 'Pacific/Auckland (New Zealand)', region: 'Pacific' },

  // Africa
  { value: 'Africa/Cairo', label: 'Africa/Cairo (Egypt)', region: 'Africa' },
  { value: 'Africa/Johannesburg', label: 'Africa/Johannesburg (South Africa)', region: 'Africa' },
  { value: 'Africa/Lagos', label: 'Africa/Lagos (Nigeria)', region: 'Africa' },

  // UTC
  { value: 'UTC', label: 'UTC (Coordinated Universal Time)', region: 'UTC' },
];

/**
 * Get all common timezones (European first, then others)
 */
export function getAllCommonTimezones(): Timezone[] {
  return [...COMMON_EUROPEAN_TIMEZONES, ...COMMON_TIMEZONES];
}

/**
 * Get timezone by value
 */
export function getTimezoneByValue(value: string): Timezone | undefined {
  return getAllCommonTimezones().find(tz => tz.value === value);
}

/**
 * Group timezones by region
 */
export function groupTimezonesByRegion(timezones: Timezone[]): Map<string, Timezone[]> {
  const grouped = new Map<string, Timezone[]>();

  for (const tz of timezones) {
    const region = tz.region;
    if (!grouped.has(region)) {
      grouped.set(region, []);
    }
    grouped.get(region)!.push(tz);
  }

  return grouped;
}
