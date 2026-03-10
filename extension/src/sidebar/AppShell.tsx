import { useState, type ReactNode } from 'react';
import PersistentNav from './components/PersistentNav';
import GoPage from './pages/GoPage';
import { useAppStore } from './store';

interface AppShellProps {
  children: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const { currentView } = useAppStore();
  const hideNav = currentView === 'auth' || currentView === 'setup';
  const [goOpen, setGoOpen] = useState(false);

  return (
    <div className="flex flex-col bg-gray-50" style={{ height: '100vh' }}>
      <div className="flex-1 overflow-auto min-h-0 relative">
        {children}

        {/* Backdrop — closes sheet on tap */}
        <div
          onClick={() => setGoOpen(false)}
          style={{
            position: 'absolute', inset: 0, zIndex: 40,
            background: 'rgba(0,0,0,0.35)',
            opacity: goOpen ? 1 : 0,
            pointerEvents: goOpen ? 'auto' : 'none',
            transition: 'opacity 0.25s ease',
          }}
        />

        {/* Go bottom sheet */}
        <div
          style={{
            position: 'absolute', left: 0, right: 0, bottom: 0, zIndex: 50,
            maxHeight: '72%',
            transform: goOpen ? 'translateY(0)' : 'translateY(100%)',
            transition: 'transform 0.28s cubic-bezier(0.32,0.72,0,1)',
            borderRadius: '16px 16px 0 0',
            overflow: 'hidden',
            boxShadow: '0 -4px 24px rgba(0,0,0,0.18)',
          }}
        >
          <GoPage onClose={() => setGoOpen(false)} />
        </div>
      </div>

      {!hideNav && (
        <PersistentNav
          goOpen={goOpen}
          onGoToggle={() => setGoOpen(o => !o)}
        />
      )}
    </div>
  );
}
