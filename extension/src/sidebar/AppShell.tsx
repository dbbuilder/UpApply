import { useState, type ReactNode } from 'react';
import PersistentNav, { getNavMode, HELP_CONTENT } from './components/PersistentNav';
import GoPage from './pages/GoPage';
import { useAppStore } from './store';

interface AppShellProps {
  children: ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const { currentView } = useAppStore();
  const hideNav = currentView === 'auth' || currentView === 'setup';
  const [goOpen, setGoOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const helpText = HELP_CONTENT[getNavMode(currentView)];

  return (
    // The outer shell is the positioning context for the Go sheet + backdrop.
    // It must NOT be a scroll container so that position:absolute children stay
    // anchored to the visible viewport, not to scrollable content height.
    <div className="flex flex-col bg-gray-50 relative" style={{ height: '100vh' }}>

      {/* Backdrop — closes Go sheet on tap */}
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

      {/* Go bottom sheet — anchored to shell bottom, never scrolls with content */}
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

      {/* Top action strip — Go + Help, always at the top of every tab */}
      {!hideNav && (
        <div className="flex-shrink-0 flex items-center justify-end gap-1 px-2 py-1 bg-white border-b border-gray-100">
          {helpOpen && (
            <p className="flex-1 text-[10px] text-gray-500 leading-snug px-1 mr-1">{helpText}</p>
          )}
          <button
            type="button"
            onClick={() => setHelpOpen(o => !o)}
            className={`text-[11px] px-2 py-0.5 rounded-full transition-colors ${
              helpOpen
                ? 'bg-gray-100 text-gray-700'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
            }`}
          >
            ?
          </button>
          <button
            type="button"
            onClick={() => { setGoOpen(o => !o); setHelpOpen(false); }}
            className={`text-[11px] px-2 py-0.5 rounded-full transition-colors font-medium ${
              goOpen
                ? 'bg-emerald-100 text-emerald-700'
                : 'text-emerald-600 hover:bg-emerald-50'
            }`}
          >
            {goOpen ? '✕' : '↗ Go'}
          </button>
        </div>
      )}

      {/* Page content — the only scrollable container */}
      <div className="flex-1 overflow-auto min-h-0 pb-1">
        {children}
      </div>

      {!hideNav && <PersistentNav goOpen={goOpen} />}
    </div>
  );
}
