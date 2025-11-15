import { useState, useEffect } from 'react';

/**
 * Hook to check if a media query matches
 * @param query - CSS media query string (e.g., "(max-width: 768px)")
 * @returns boolean indicating if the query matches
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(query);

    // Set initial value
    if (media.matches !== matches) {
      setMatches(media.matches);
    }

    // Create listener
    const listener = () => setMatches(media.matches);

    // Add listener (modern browsers)
    if (media.addEventListener) {
      media.addEventListener('change', listener);
      return () => media.removeEventListener('change', listener);
    } else {
      // Fallback for older browsers
      media.addListener(listener);
      return () => media.removeListener(listener);
    }
  }, [matches, query]);

  return matches;
}

/**
 * Convenience hook to check if viewport is mobile size
 * Mobile: < 768px (matches Tailwind's md breakpoint)
 */
export const useIsMobile = () => useMediaQuery('(max-width: 767px)');

/**
 * Convenience hook to check if viewport is tablet size
 * Tablet: 768px - 1023px (between md and lg)
 */
export const useIsTablet = () => useMediaQuery('(min-width: 768px) and (max-width: 1023px)');

/**
 * Convenience hook to check if viewport is desktop size
 * Desktop: >= 1024px (matches Tailwind's lg breakpoint)
 */
export const useIsDesktop = () => useMediaQuery('(min-width: 1024px)');

/**
 * Convenience hook to check if device supports touch
 */
export const useIsTouchDevice = () => {
  const [isTouch, setIsTouch] = useState(false);

  useEffect(() => {
    setIsTouch('ontouchstart' in window || navigator.maxTouchPoints > 0);
  }, []);

  return isTouch;
};
