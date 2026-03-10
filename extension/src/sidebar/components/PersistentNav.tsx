import { useAppStore } from '../store';

type NavMode = 'me' | 'find' | 'apply' | 'track';

type ViewType =
  | 'auth' | 'setup' | 'generator' | 'me' | 'find' | 'track' | 'go'
  | 'memories' | 'history' | 'analytics' | 'feedback' | 'skills' | 'profile';

const ME_VIEWS: string[]    = ['me', 'profile', 'skills', 'memories', 'setup'];
const FIND_VIEWS: string[]  = ['find', 'scored'];
const TRACK_VIEWS: string[] = ['track', 'history', 'analytics', 'feedback'];

function getMode(view: string): NavMode {
  if (ME_VIEWS.includes(view))    return 'me';
  if (FIND_VIEWS.includes(view))  return 'find';
  if (TRACK_VIEWS.includes(view)) return 'track';
  return 'apply';
}

interface NavItem {
  mode: NavMode;
  icon: string;
  label: string;
  targetView: ViewType;
  dot?: boolean;
}

interface PersistentNavProps {
  goOpen: boolean;
  onGoToggle: () => void;
}

export default function PersistentNav({ goOpen, onGoToggle }: PersistentNavProps) {
  const { currentView, setCurrentView, currentJob } = useAppStore();
  const activeMode = getMode(currentView);
  const hasJob = !!currentJob?.title;

  const items: NavItem[] = [
    { mode: 'me',    icon: '👤', label: 'Me',    targetView: 'me' },
    { mode: 'find',  icon: '🔍', label: 'Find',  targetView: 'find' },
    { mode: 'apply', icon: '✍️', label: 'Apply', targetView: 'generator', dot: hasJob },
    { mode: 'track', icon: '📊', label: 'Track', targetView: 'track' },
  ];

  return (
    <nav className="flex border-t border-gray-200 bg-white flex-shrink-0" style={{ height: '56px' }}>
      {items.map(({ mode, icon, label, targetView, dot }) => {
        const active = activeMode === mode && !goOpen;
        return (
          <button
            key={mode}
            type="button"
            onClick={() => setCurrentView(targetView)}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 relative transition-colors ${
              active
                ? 'text-emerald-600 border-t-2 border-emerald-500'
                : 'text-gray-400 border-t-2 border-transparent hover:text-gray-600'
            }`}
          >
            <span className="text-lg leading-none relative">
              {icon}
              {dot && (
                <span className="absolute -top-0.5 -right-1 w-2 h-2 rounded-full bg-emerald-500" />
              )}
            </span>
            <span className={`text-xs font-medium ${active ? 'text-emerald-600' : 'text-gray-400'}`}>
              {label}
            </span>
          </button>
        );
      })}

      {/* Go — visually distinct: always emerald, acts as sheet toggle not a tab */}
      <button
        type="button"
        onClick={onGoToggle}
        className={`flex flex-col items-center justify-center gap-0.5 px-3 transition-colors border-t-2 ${
          goOpen
            ? 'text-emerald-700 border-emerald-600 bg-emerald-50'
            : 'text-emerald-500 border-transparent hover:text-emerald-600'
        }`}
      >
        <span className="text-lg leading-none">{goOpen ? '✕' : '↗'}</span>
        <span className="text-xs font-medium">Go</span>
      </button>
    </nav>
  );
}
