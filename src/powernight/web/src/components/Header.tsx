import React from 'react';
import { Link, useLocation } from 'react-router-dom';

const Header: React.FC = () => {
  const location = useLocation();

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
          </div>

          {/* Navigation */}
          <nav className="flex space-x-8">
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

          {/* Empty div to maintain layout balance */}
          <div className="flex items-center">
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
