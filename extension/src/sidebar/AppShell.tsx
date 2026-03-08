import { type ReactNode } from 'react';
import PersistentNav from './components/PersistentNav';
import { useAppStore } from './store';

interface AppShellProps {
  children: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const { currentView } = useAppStore();
  const hideNav = currentView === 'auth' || currentView === 'setup';

  return (
    <div className="flex flex-col bg-gray-50" style={{ height: '100vh' }}>
      <div className="flex-1 overflow-auto min-h-0">
        {children}
      </div>
      {!hideNav && <PersistentNav />}
    </div>
  );
}
