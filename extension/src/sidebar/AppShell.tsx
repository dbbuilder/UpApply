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
    // The outer shell is the positioning context for the Go sheet + backdrop.
    // It must NOT be a scroll container so that position:absolute children stay
    // anchored to the visible viewport, not to scrollable content height.
    <div className="flex flex-col bg-gray-50 relative" style={{ height: '100vh' }}>

      {/* Backdrop — closes sheet on tap. Sits over content, under sheet. */}
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

      {/* Go bottom sheet — anchored to the shell's bottom, never scrolls with content */}
      <div
        style={{
          position: 'absolute', left: 0, right: 0, bottom: hideNav ? 0 : 52, zIndex: 50,
          maxHeight: '72%',
          transform: goOpen ? 'translateY(0)' : 'translateY(110%)',
          transition: 'transform 0.28s cubic-bezier(0.32,0.72,0,1)',
          borderRadius: '16px 16px 0 0',
          overflow: 'hidden',
          boxShadow: '0 -4px 24px rgba(0,0,0,0.18)',
        }}
      >
        <GoPage onClose={() => setGoOpen(false)} />
      </div>

      {/* Page content — the only scrollable container */}
      <div className="flex-1 overflow-auto min-h-0 pb-1">
        {children}
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
