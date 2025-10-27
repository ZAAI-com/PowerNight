import React, { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ErrorBoundary } from './components/ErrorBoundary';
import Header from './components/Header';
import { LoadingSpinner } from './components/LoadingSpinner';
import { useAuth } from './hooks/useAuth';
import { TimezoneProvider } from './contexts/TimezoneContext';
import Login from './pages/Login';

// Lazy load pages for better performance
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const Settings = React.lazy(() => import('./pages/Settings'));
const Planner = React.lazy(() => import('./pages/Planner'));
const History = React.lazy(() => import('./pages/History'));

const AppContent: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();

  // Show loading spinner while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" text="Checking authentication..." />
      </div>
    );
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <Login />;
  }

  // Show main app if authenticated
  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="flex-1 pt-16">
          <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center">
              <LoadingSpinner size="lg" text="Loading..." />
            </div>
          }>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/planner" element={<Planner />} />
              <Route path="/history" element={<History />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </Router>
  );
};

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <TimezoneProvider>
        <AppContent />
      </TimezoneProvider>
    </ErrorBoundary>
  );
};

export default App;
