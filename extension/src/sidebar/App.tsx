import { useEffect } from 'react';
import { useAppStore } from './store';
import AppShell from './AppShell';
import AuthPage from './pages/Auth';
import SetupPage from './pages/Setup';
import GeneratorPage from './pages/Generator';
import MemoriesPage from './pages/Memories';
import HistoryPage from './pages/History';
import AnalyticsPage from './pages/Analytics';
import BetaFeedbackPage from './pages/BetaFeedback';
import SkillsPage from './pages/Skills';
import EditProfilePage from './pages/EditProfile';
import MePage from './pages/MePage';
import FindPage from './pages/FindPage';
import TrackPage from './pages/TrackPage';
import GoPage from './pages/GoPage';

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
      case 'me':
        return <MePage />;
      case 'find':
        return <FindPage />;
      case 'track':
        return <TrackPage />;
      case 'go':
        return <GoPage />;
      case 'memories':
        return <MemoriesPage />;
      case 'history':
        return <HistoryPage />;
      case 'analytics':
        return <AnalyticsPage />;
      case 'feedback':
        return <BetaFeedbackPage />;
      case 'skills':
        return <SkillsPage />;
      case 'profile':
        return <EditProfilePage />;
      default:
        return <GeneratorPage />;
    }
  };

  return (
    <AppShell>
      {renderView()}
    </AppShell>
  );
}

export default App;
