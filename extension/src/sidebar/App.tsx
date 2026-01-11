import { useEffect } from 'react';
import { useAppStore } from './store';
import AuthPage from './pages/Auth';
import SetupPage from './pages/Setup';
import GeneratorPage from './pages/Generator';
import MemoriesPage from './pages/Memories';
import HistoryPage from './pages/History';
import AnalyticsPage from './pages/Analytics';

function App() {
  const { currentView, isLoading, checkAuth } = useAppStore();

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse-slow text-gray-500">Loading...</div>
      </div>
    );
  }

  const renderView = () => {
    switch (currentView) {
      case 'auth':
        return <AuthPage />;
      case 'setup':
        return <SetupPage />;
      case 'generator':
        return <GeneratorPage />;
      case 'memories':
        return <MemoriesPage />;
      case 'history':
        return <HistoryPage />;
      case 'analytics':
        return <AnalyticsPage />;
      default:
        return <GeneratorPage />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {renderView()}
    </div>
  );
}

export default App;
