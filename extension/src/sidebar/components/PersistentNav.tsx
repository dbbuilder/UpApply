import { useAppStore } from '../store';

type NavMode = 'me' | 'find' | 'apply' | 'track' | 'go';

type ViewType =
  | 'auth'
  | 'setup'
  | 'generator'
  | 'me'
  | 'find'
  | 'track'
  | 'go'
  | 'memories'
  | 'history'
  | 'analytics'
  | 'feedback'
  | 'skills'
  | 'profile';

const ME_VIEWS: string[] = ['me', 'profile', 'skills', 'memories', 'setup'];
const FIND_VIEWS: string[] = ['find', 'scored'];
const TRACK_VIEWS: string[] = ['track', 'history', 'analytics', 'feedback'];
const GO_VIEWS: string[] = ['go'];

function getMode(view: string): NavMode {
  if (ME_VIEWS.includes(view)) return 'me';
  if (FIND_VIEWS.includes(view)) return 'find';
  if (TRACK_VIEWS.includes(view)) return 'track';
  if (GO_VIEWS.includes(view)) return 'go';
  return 'apply';
}

interface NavItem {
  mode: NavMode;
  icon: string;
  label: string;
  targetView: ViewType;
  dot?: boolean;
}

export default function PersistentNav() {
  const { currentView, setCurrentView, currentJob } = useAppStore();
  const activeMode = getMode(currentView);
  const hasJob = !!currentJob?.title;

  const items: NavItem[] = [
    { mode: 'me',    icon: '👤', label: 'Me',    targetView: 'me' },
    { mode: 'find',  icon: '🔍', label: 'Find',  targetView: 'find' },
    { mode: 'apply', icon: '✍️', label: 'Apply', targetView: 'generator', dot: hasJob },
    { mode: 'track', icon: '📊', label: 'Track', targetView: 'track' },
    { mode: 'go',    icon: '🔗', label: 'Go',    targetView: 'go' },
  ];

  return (
    <nav className="flex border-t border-gray-200 bg-white flex-shrink-0" style={{ height: '56px' }}>
      {items.map(({ mode, icon, label, targetView, dot }) => {
        const active = activeMode === mode;
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
    </nav>
  );
}
