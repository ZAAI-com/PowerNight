import React, { useRef, useState, useEffect } from 'react';

interface ResponsiveTableProps {
  children: React.ReactNode;
  className?: string;
}

/**
 * Responsive table wrapper that provides:
 * - Horizontal scroll on mobile
 * - Scroll indicators (shadows) to show more content
 * - Touch-friendly scrolling
 */
export const ResponsiveTable: React.FC<ResponsiveTableProps> = ({ children, className = '' }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftShadow, setShowLeftShadow] = useState(false);
  const [showRightShadow, setShowRightShadow] = useState(false);

  // Check scroll position to show/hide shadows
  const checkScroll = () => {
    const element = scrollRef.current;
    if (!element) return;

    const { scrollLeft, scrollWidth, clientWidth } = element;

    // Show left shadow if scrolled right
    setShowLeftShadow(scrollLeft > 10);

    // Show right shadow if there's more content to the right
    setShowRightShadow(scrollLeft < scrollWidth - clientWidth - 10);
  };

  useEffect(() => {
    checkScroll();
    const element = scrollRef.current;
    if (!element) return;

    // Add scroll listener
    element.addEventListener('scroll', checkScroll);

    // Check on resize
    const resizeObserver = new ResizeObserver(checkScroll);
    resizeObserver.observe(element);

    return () => {
      element.removeEventListener('scroll', checkScroll);
      resizeObserver.disconnect();
    };
  }, []);

  // Recheck when children change (table data updates)
  useEffect(() => {
    checkScroll();
  }, [children]);

  return (
    <div className="relative">
      {/* Left scroll indicator */}
      <div
        className={`absolute left-0 top-0 bottom-0 w-4 bg-gradient-to-r from-gray-900/10 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
          showLeftShadow ? 'opacity-100' : 'opacity-0'
        }`}
        aria-hidden="true"
      />

      {/* Right scroll indicator */}
      <div
        className={`absolute right-0 top-0 bottom-0 w-4 bg-gradient-to-l from-gray-900/10 to-transparent pointer-events-none z-10 transition-opacity duration-200 ${
          showRightShadow ? 'opacity-100' : 'opacity-0'
        }`}
        aria-hidden="true"
      />

      {/* Scrollable container */}
      <div
        ref={scrollRef}
        className={`overflow-x-auto -mx-3 px-3 sm:mx-0 sm:px-0 ${className}`}
        style={{
          // Enable momentum scrolling on iOS
          WebkitOverflowScrolling: 'touch',
          // Show scrollbar on mobile for better UX
          scrollbarWidth: 'thin',
        }}
      >
        {children}
      </div>

      {/* Hint text for mobile users (only shown on first render) */}
      {showRightShadow && (
        <div className="md:hidden text-xs text-gray-500 text-center mt-2 animate-pulse">
          ← Swipe to see more →
        </div>
      )}
    </div>
  );
};
