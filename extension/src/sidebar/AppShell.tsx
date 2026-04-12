import { useState, type ReactNode } from 'react';
import PersistentNav, { getNavMode, HELP_CONTENT } from './components/PersistentNav';
import { useAppStore } from './store';

interface AppShellProps {
  children: ReactNode;
}

const PAGE_TITLES: Record<string, string> = {
  generator: '✍️ Apply',
  me: '👤 Me',
  profile: '👤 Me',
  skills: '👤 Me',
  memories: '👤 Me',
  find: '🔍 Find',
  scored: '🔍 Find',
  queue: '📋 Queue',
  track: '📊 Track',
  history: '📊 Track',
  analytics: '📊 Track',
  feedback: '📊 Track',
  insights: '💡 Insights',
  import: '⇅ Sync',
  suggestions: '🤖 Agent',
};

const UPWORK = 'https://www.upwork.com';
const UPWORK_LINKS = [
  { icon: '🔔', label: 'Notifications', url: `${UPWORK}/ab/notifications/`,         desc: 'Bell feed — score jobs here' },
  { icon: '🔖', label: 'Saved Jobs',    url: `${UPWORK}/nx/search/jobs/saved/`,      desc: 'Bookmarked jobs — score them' },
  { icon: '🔍', label: 'Find Work',     url: `${UPWORK}/nx/find-work/`,              desc: 'Search & browse listings' },
  { icon: '📋', label: 'Contracts',     url: `${UPWORK}/nx/wm/freelancer/contracts`, desc: 'Active & past contracts' },
  { icon: '📝', label: 'Proposals',     url: `${UPWORK}/nx/proposals/`,              desc: 'Sent proposals & drafts' },
  { icon: '💬', label: 'Messages',      url: `${UPWORK}/nx/message-center/`,         desc: 'Client conversations' },
  { icon: '📊', label: 'Reports',       url: `${UPWORK}/nx/reports/`,                desc: 'Earnings & time reports' },
  { icon: '👤', label: 'Profile',       url: `${UPWORK}/freelancers/settings/`,      desc: 'Public profile & settings' },
];

const NAV_ITEMS = [
  { icon: '👤', label: 'Me',         view: 'me' },
  { icon: '🔍', label: 'Find',       view: 'find' },
  { icon: '✍️', label: 'Apply',      view: 'generator' },
  { icon: '🤖', label: 'Agent',      view: 'suggestions' },
  { icon: '📋', label: 'Queue',      view: 'queue' },
  { icon: '📊', label: 'Track',      view: 'track' },
  { icon: '💡', label: 'Insight',    view: 'insights' },
  { icon: '⇅',  label: 'Sync',       view: 'import' },
] as const;

function navigateTo(url: string, onDone?: () => void) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0]?.id;
    if (tabId) chrome.tabs.update(tabId, { url });
  });
  if (onDone) setTimeout(onDone, 380);
}

export default function AppShell({ children }: AppShellProps) {
  const { currentView, setCurrentView, logout } = useAppStore();
  const hideNav = currentView === 'auth' || currentView === 'setup';
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const helpText = HELP_CONTENT[getNavMode(currentView)];

  return (
    <div className="flex flex-col bg-gray-50 relative" style={{ height: '100vh' }}>

      {/* Backdrop — closes menu on tap */}
      <div
        onClick={() => setMenuOpen(false)}
        style={{
          position: 'absolute', inset: 0, zIndex: 40,
          background: 'rgba(0,0,0,0.35)',
          opacity: menuOpen ? 1 : 0,
          pointerEvents: menuOpen ? 'auto' : 'none',
          transition: 'opacity 0.22s ease',
        }}
      />

      {/* Hamburger drawer — slides in from left */}
      <div
        style={{
          position: 'absolute', top: 0, left: 0, bottom: 0, width: '100%', zIndex: 50,
          transform: menuOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 0.25s cubic-bezier(0.32,0.72,0,1)',
          background: 'white',
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
        }}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 flex-shrink-0">
          <span className="font-semibold text-gray-800 text-sm">UpApply</span>
          <button type="button" onClick={() => setMenuOpen(false)} className="text-gray-400 hover:text-gray-700 text-lg leading-none">✕</button>
        </div>

        {/* Upwork quick links */}
        <div className="p-3 flex-shrink-0">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-2">Go to Upwork</p>
          <div className="grid grid-cols-2 gap-2">
            {UPWORK_LINKS.map((link) => (
              <button
                key={link.url}
                type="button"
                onClick={() => navigateTo(link.url, () => setMenuOpen(false))}
                className="flex items-start gap-2 p-2.5 bg-gray-50 border border-gray-100 rounded-xl text-left hover:border-emerald-200 hover:bg-emerald-50 active:scale-95 transition-all group"
              >
                <span className="text-base leading-none mt-0.5 flex-shrink-0">{link.icon}</span>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-gray-800 group-hover:text-emerald-700">{link.label}</p>
                  <p className="text-[10px] text-gray-400 leading-tight mt-0.5">{link.desc}</p>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Tab navigation */}
        <div className="px-3 pb-4 flex-shrink-0">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-2 mt-1">Navigate</p>
          <div className="space-y-0.5">
            {NAV_ITEMS.map(({ icon, label, view }) => {
              const active = currentView === view || (view === 'generator' && currentView === 'generator');
              return (
                <button
                  key={view}
                  type="button"
                  onClick={() => { setCurrentView(view); setMenuOpen(false); }}
                  className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                    active ? 'bg-emerald-50 text-emerald-700 font-medium' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <span className="text-base leading-none w-5 text-center">{icon}</span>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Unified top bar */}
      {!hideNav && (
        <div className="flex-shrink-0 flex items-center justify-between px-3 py-2 bg-white border-b border-gray-100">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMenuOpen(o => !o)}
              className="text-gray-500 hover:text-gray-800 p-1 rounded transition-colors"
              aria-label="Menu"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect y="2" width="16" height="2" rx="1"/>
                <rect y="7" width="16" height="2" rx="1"/>
                <rect y="12" width="16" height="2" rx="1"/>
              </svg>
            </button>
            <h1 className="font-bold text-gray-900 text-sm">{PAGE_TITLES[currentView] ?? '✍️ Apply'}</h1>
          </div>
          <div className="flex items-center gap-2">
            {helpOpen && (
              <span className="text-[10px] text-gray-500 leading-snug max-w-[160px] text-right">{helpText}</span>
            )}
            <button
              type="button"
              onClick={() => setHelpOpen(o => !o)}
              className={`text-xs px-1.5 py-0.5 rounded-full transition-colors ${helpOpen ? 'bg-gray-100 text-gray-700' : 'text-gray-400 hover:text-gray-600'}`}
            >?</button>
            <button
              type="button"
              onClick={logout}
              className="text-gray-400 hover:text-gray-600 text-xs"
            >Logout</button>
          </div>
        </div>
      )}

      {/* Page content — only scrollable container. overscroll-none prevents elastic bounce
          revealing content behind the nav. pb-14 ensures last element clears the nav bar. */}
      <div className="flex-1 overflow-auto min-h-0 overscroll-none pb-14">
        {children}
      </div>

      {!hideNav && <PersistentNav />}
    </div>
  );
}
