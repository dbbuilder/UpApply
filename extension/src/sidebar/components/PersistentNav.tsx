import { useState } from 'react';
import { useAppStore } from '../store';

type NavMode = 'me' | 'find' | 'apply' | 'queue' | 'track' | 'insights' | 'import';

type ViewType =
  | 'auth' | 'setup' | 'generator' | 'me' | 'find' | 'track' | 'queue' | 'go'
  | 'memories' | 'history' | 'analytics' | 'feedback' | 'skills' | 'profile'
  | 'insights' | 'import';

const ME_VIEWS: string[]      = ['me', 'profile', 'skills', 'memories', 'setup'];
const FIND_VIEWS: string[]    = ['find', 'scored'];
const QUEUE_VIEWS: string[]   = ['queue'];
const TRACK_VIEWS: string[]   = ['track', 'history', 'analytics', 'feedback'];
const INSIGHTS_VIEWS: string[] = ['insights'];
const IMPORT_VIEWS: string[]  = ['import'];

function getMode(view: string): NavMode {
  if (ME_VIEWS.includes(view))      return 'me';
  if (FIND_VIEWS.includes(view))    return 'find';
  if (QUEUE_VIEWS.includes(view))   return 'queue';
  if (TRACK_VIEWS.includes(view))   return 'track';
  if (INSIGHTS_VIEWS.includes(view)) return 'insights';
  if (IMPORT_VIEWS.includes(view))  return 'import';
  return 'apply';
}

const HELP_CONTENT: Record<NavMode | 'apply', string> = {
  me:       'Edit your profile, skills, and memories that AI uses to write cover letters.',
  find:     'Browse scored jobs. Stars = match strength. Rate jobs to train your profile.',
  apply:    'Score the current Upwork job and generate a tailored cover letter.',
  queue:    'Jobs you\'ve saved or are actively applying to. Use Apply → to open with your cover letter pre-filled.',
  track:    'Pipeline funnel, work log, proposal history, and activity trends.',
  insights: 'AI analysis of your proposal history — what\'s landing, what to target, and how to position.',
  import:   'Data overview — corpus totals, funnel stats, and import tools to seed from Upwork.',
};

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
  const [helpOpen, setHelpOpen] = useState(false);

  const items: NavItem[] = [
    { mode: 'me',       icon: '👤', label: 'Me',     targetView: 'me' },
    { mode: 'find',     icon: '🔍', label: 'Find',   targetView: 'find' },
    { mode: 'apply',    icon: '✍️', label: 'Apply',  targetView: 'generator', dot: hasJob },
    { mode: 'queue',    icon: '📋', label: 'Queue',  targetView: 'queue' },
    { mode: 'track',    icon: '📊', label: 'Track',  targetView: 'track' },
    { mode: 'insights', icon: '💡', label: 'Insight', targetView: 'insights' },
    { mode: 'import',   icon: '⬇',  label: 'Data',   targetView: 'import' },
  ];

  const helpText = HELP_CONTENT[activeMode];

  return (
    <div className="flex-shrink-0 relative">
      {/* Contextual help tooltip */}
      {helpOpen && (
        <div
          className="absolute bottom-full left-2 right-2 mb-1 bg-gray-900 text-white text-[11px] rounded-lg px-3 py-2 shadow-lg z-50 leading-snug"
          style={{ pointerEvents: 'none' }}
        >
          {helpText}
        </div>
      )}

      <nav className="flex border-t border-gray-200 bg-white" style={{ height: '52px' }}>
        {items.map(({ mode, icon, label, targetView, dot }) => {
          const active = activeMode === mode && !goOpen;
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
              <span className="text-base leading-none relative">
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

        {/* Go — visually distinct */}
        <button
          type="button"
          onClick={onGoToggle}
          className={`flex flex-col items-center justify-center gap-0 px-2 transition-colors border-t-2 ${
            goOpen
              ? 'text-emerald-700 border-emerald-600 bg-emerald-50'
              : 'text-emerald-500 border-transparent hover:text-emerald-600'
          }`}
        >
          <span className="text-base leading-none">{goOpen ? '✕' : '↗'}</span>
          <span className="text-[9px] font-medium">Go</span>
        </button>

        {/* Help ? button */}
        <button
          type="button"
          onMouseEnter={() => setHelpOpen(true)}
          onMouseLeave={() => setHelpOpen(false)}
          onClick={() => setHelpOpen(o => !o)}
          className="flex flex-col items-center justify-center gap-0 px-2 text-gray-300 hover:text-gray-500 border-t-2 border-transparent transition-colors"
          title={helpText}
        >
          <span className="text-base leading-none">?</span>
          <span className="text-[9px] font-medium">Help</span>
        </button>
      </nav>
    </div>
  );
}
