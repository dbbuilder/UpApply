import { useAppStore } from '../store';

type NavMode = 'me' | 'find' | 'apply' | 'queue' | 'track' | 'insights' | 'import' | 'suggestions';

type ViewType =
  | 'auth' | 'setup' | 'generator' | 'me' | 'find' | 'track' | 'queue' | 'go'
  | 'memories' | 'history' | 'analytics' | 'feedback' | 'skills' | 'profile'
  | 'insights' | 'import' | 'suggestions' | 'guardrails';

const ME_VIEWS: string[]          = ['me', 'profile', 'skills', 'memories', 'setup'];
const FIND_VIEWS: string[]        = ['find', 'scored'];
const QUEUE_VIEWS: string[]       = ['queue'];
const TRACK_VIEWS: string[]       = ['track', 'history', 'analytics', 'feedback'];
const INSIGHTS_VIEWS: string[]    = ['insights'];
const IMPORT_VIEWS: string[]      = ['import'];
const SUGGESTIONS_VIEWS: string[] = ['suggestions', 'guardrails'];

export function getNavMode(view: string): NavMode {
  if (ME_VIEWS.includes(view))          return 'me';
  if (FIND_VIEWS.includes(view))        return 'find';
  if (QUEUE_VIEWS.includes(view))       return 'queue';
  if (TRACK_VIEWS.includes(view))       return 'track';
  if (INSIGHTS_VIEWS.includes(view))    return 'insights';
  if (IMPORT_VIEWS.includes(view))      return 'import';
  if (SUGGESTIONS_VIEWS.includes(view)) return 'suggestions';
  return 'apply';
}

export const HELP_CONTENT: Record<NavMode, string> = {
  me:          'Edit your profile, skills, and memories that AI uses to write cover letters.',
  find:        'Browse scored jobs. Stars = match strength. Rate jobs to train your profile.',
  apply:       'Score the current Upwork job and generate a tailored cover letter.',
  queue:       'Jobs you\'ve saved or are actively applying to. Use Apply → to open with your cover letter pre-filled.',
  track:       'Pipeline funnel, work log, proposal history, and activity trends.',
  insights:    'AI analysis of your proposal history — what\'s landing, what to target, and how to position.',
  import:      'Sync — corpus overview (totals, funnel stats) and import tools to seed from Upwork.',
  suggestions: 'Agent-discovered jobs. Approve to move to Queue, pass to skip. Runs daily at 6am PT.',
};

interface NavItem {
  mode: NavMode;
  icon: string;
  label: string;
  targetView: ViewType;
  dot?: boolean;
}

export default function PersistentNav() {
  const { currentView, setCurrentView, currentJob } = useAppStore();
  const activeMode = getNavMode(currentView);
  const hasJob = !!currentJob?.title;

  const items: NavItem[] = [
    { mode: 'me',          icon: '👤', label: 'Me',       targetView: 'me' },
    { mode: 'find',        icon: '🔍', label: 'Find',     targetView: 'find' },
    { mode: 'apply',       icon: '✍️', label: 'Apply',    targetView: 'generator', dot: hasJob },
    { mode: 'suggestions', icon: '🤖', label: 'Agent',    targetView: 'suggestions' },
    { mode: 'queue',       icon: '📋', label: 'Queue',    targetView: 'queue' },
    { mode: 'track',       icon: '📊', label: 'Track',    targetView: 'track' },
    { mode: 'import',      icon: '⇅',  label: 'Sync',     targetView: 'import' },
  ];

  return (
    <div className="flex-shrink-0 w-full">
      <nav className="flex border-t border-gray-200 bg-white w-full overflow-hidden" style={{ height: '52px' }}>
        {items.map(({ mode, icon, label, targetView, dot }) => {
          const active = activeMode === mode;
          return (
            <button
              key={mode}
              type="button"
              onClick={() => setCurrentView(targetView)}
              className={`flex-1 flex flex-col items-center justify-center gap-0 relative transition-colors min-w-0 ${
                active
                  ? 'text-emerald-600 border-t-2 border-emerald-500'
                  : 'text-gray-400 border-t-2 border-transparent hover:text-gray-600'
              }`}
            >
              <span className="text-sm leading-none relative">
                {icon}
                {dot && (
                  <span className="absolute -top-0.5 -right-1 w-1.5 h-1.5 rounded-full bg-emerald-500" />
                )}
              </span>
              <span className={`text-[9px] font-medium truncate w-full text-center px-0.5 ${active ? 'text-emerald-600' : 'text-gray-400'}`}>
                {label}
              </span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
