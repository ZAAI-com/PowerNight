import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { api } from '../utils/api';

type HealthState = 'healthy' | 'degraded' | 'unhealthy' | 'unreachable' | 'unknown';

const HEALTH_POLL_INTERVAL_MS = 30000;

const HEALTH_DOT_STYLES: Record<HealthState, string> = {
  healthy: 'bg-green-400',
  degraded: 'bg-yellow-400',
  unhealthy: 'bg-red-500',
  unreachable: 'bg-red-500',
  unknown: 'bg-gray-400',
};

const HEALTH_LABELS: Record<HealthState, string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  unhealthy: 'Unhealthy',
  unreachable: 'Unreachable',
  unknown: 'Checking...',
};

const Header: React.FC = () => {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState<HealthState>('unknown');

  // Poll system health every 30 seconds
  useEffect(() => {
    let cancelled = false;

    const fetchHealth = async () => {
      try {
        const data = await api.getHealth();
        if (cancelled) return;
        setHealth(data.status);
      } catch (err) {
        if (cancelled) return;
        // /api/v1/health returns HTTP 503 when unhealthy, which axios
        // treats as an error; the response body still carries the status.
        const responseStatus = (err as { response?: { data?: { status?: string } } })?.response?.data?.status;
        if (responseStatus === 'degraded' || responseStatus === 'unhealthy') {
          setHealth(responseStatus);
        } else {
          setHealth('unreachable');
        }
      }
    };

    fetchHealth();
    const intervalId = window.setInterval(fetchHealth, HEALTH_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, []);

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navItems = [
    { path: '/', label: 'Dashboard' },
    { path: '/planner', label: 'Planner' },
    { path: '/history', label: 'History' },
    { path: '/settings', label: 'Settings' },
  ];

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-gradient-to-r from-blue-600 via-blue-500 to-purple-600 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo and Title */}
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <h1 className="text-2xl font-bold text-white">
                PowerNight
              </h1>
            </div>
            <span
              className={`ml-3 h-2.5 w-2.5 rounded-full ${HEALTH_DOT_STYLES[health]}`}
              title={`System status: ${HEALTH_LABELS[health]}`}
              aria-label={`System status: ${HEALTH_LABELS[health]}`}
              role="status"
              data-testid="health-indicator"
            />
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex space-x-8">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                className={`px-3 py-2 rounded-md text-sm font-bold transition-colors ${
                  isActive(item.path)
                    ? 'bg-white/20 text-white border border-white/30'
                    : 'text-white/90 hover:text-white hover:bg-white/10'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          {/* Empty div to maintain layout balance (desktop only) */}
          <div className="hidden md:flex items-center">
          </div>

          {/* Mobile menu button */}
          <div className="flex items-center md:hidden">
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="text-white p-2 rounded-md hover:bg-white/10 focus:outline-none"
              aria-label="Toggle navigation menu"
              aria-expanded={menuOpen}
            >
              {menuOpen ? (
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Dropdown */}
        {menuOpen && (
          <div className="md:hidden border-t border-white/20 pb-3 pt-2">
            {navItems.map((item) => (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMenuOpen(false)}
                className={`block px-4 py-2 text-sm font-bold transition-colors ${
                  isActive(item.path)
                    ? 'bg-white/20 text-white'
                    : 'text-white/90 hover:text-white hover:bg-white/10'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;
