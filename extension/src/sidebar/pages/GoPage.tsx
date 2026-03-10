/**
 * GoPage — quick navigation to Upwork pages + one-click actions from the sidebar.
 */
import { useState, useEffect, useRef } from 'react';

const UPWORK = 'https://www.upwork.com';

interface QuickLink {
  icon: string;
  label: string;
  url: string;
  description: string;
}

const LINKS: QuickLink[] = [
  { icon: '🔔', label: 'Notifications', url: `${UPWORK}/ab/notifications/`,         description: 'Bell feed — score jobs here' },
  { icon: '🔖', label: 'Saved Jobs',    url: `${UPWORK}/nx/search/jobs/saved/`,      description: 'Bookmarked jobs — score them' },
  { icon: '🔍', label: 'Find Work',     url: `${UPWORK}/nx/find-work/`,              description: 'Search & browse listings' },
  { icon: '📋', label: 'Contracts',     url: `${UPWORK}/nx/wm/freelancer/contracts`, description: 'Active & past contracts' },
  { icon: '📝', label: 'Proposals',     url: `${UPWORK}/nx/proposals/`,              description: 'Sent proposals & drafts' },
  { icon: '💬', label: 'Messages',      url: `${UPWORK}/nx/message-center/`,         description: 'Client conversations' },
  { icon: '📊', label: 'Reports',       url: `${UPWORK}/nx/reports/`,                description: 'Earnings & time reports' },
  { icon: '👤', label: 'Profile',       url: `${UPWORK}/freelancers/settings/`,      description: 'Public profile & settings' },
];

function navigateTo(url: string, onDone?: () => void) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0]?.id;
    if (tabId) chrome.tabs.update(tabId, { url });
  });
  // Close the sheet after a beat so the user sees the tap register
  if (onDone) setTimeout(onDone, 380);
}

interface ImportProgress {
  stage: 'navigating' | 'scraping' | 'saving' | 'done' | 'error';
  page?: number;       // current scraping page
  total?: number;      // total pages (scraping) or total contracts (done)
  count?: number;      // contracts to save
  imported?: number;   // newly created
  updated?: number;    // updated existing
  error?: string;
}

function progressLabel(p: ImportProgress | null): string {
  if (!p) return '📥 Import Contracts';
  switch (p.stage) {
    case 'navigating': return 'Opening contracts page…';
    case 'scraping':   return p.page && p.total && p.total > 1
      ? `Scraping page ${p.page} of ${p.total}…`
      : 'Scraping contracts…';
    case 'saving':     return p.count ? `Saving ${p.count} contracts…` : 'Saving…';
    case 'done':       return '✓ Done';
    case 'error':      return '✗ Failed — retry?';
  }
}

function progressDetail(p: ImportProgress | null): string | null {
  if (!p) return null;
  if (p.stage === 'done') {
    const n = (p.imported ?? 0) + (p.updated ?? 0);
    return `${n} contract${n !== 1 ? 's' : ''} synced (${p.imported ?? 0} new, ${p.updated ?? 0} updated)`;
  }
  if (p.stage === 'error') return p.error || 'Import failed';
  return null;
}

interface GoPageProps {
  onClose?: () => void;
}

export default function GoPage({ onClose }: GoPageProps) {
  const [progress, setProgress] = useState<ImportProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isRunning = progress !== null && progress.stage !== 'done' && progress.stage !== 'error';

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startPolling = () => {
    stopPolling();
    pollRef.current = setInterval(() => {
      chrome.storage.local.get('contractImportProgress', (result) => {
        const p = result.contractImportProgress as ImportProgress | undefined;
        if (p) setProgress(p);
        if (p?.stage === 'done' || p?.stage === 'error') stopPolling();
      });
    }, 500);
  };

  useEffect(() => {
    // Check if an import is already in progress when page mounts
    chrome.storage.local.get('contractImportProgress', (result) => {
      const p = result.contractImportProgress as ImportProgress | undefined;
      if (p && p.stage !== 'done' && p.stage !== 'error') {
        setProgress(p);
        startPolling();
      }
    });
    return stopPolling;
  }, []);

  const handleImportContracts = () => {
    // Clear previous progress
    chrome.storage.local.remove('contractImportProgress');
    setProgress({ stage: 'navigating' });
    startPolling();

    chrome.runtime.sendMessage(
      { type: 'NAVIGATE_AND_IMPORT_CONTRACTS' },
      (resp: { success: boolean; imported?: number; updated?: number; total?: number; error?: string } | undefined) => {
        stopPolling();
        if (chrome.runtime.lastError || !resp) {
          setProgress({ stage: 'error', error: chrome.runtime.lastError?.message || 'No response from background' });
          return;
        }
        if (resp.success) {
          setProgress({ stage: 'done', imported: resp.imported, updated: resp.updated, total: resp.total });
        } else {
          setProgress({ stage: 'error', error: resp.error || 'Import failed' });
        }
      }
    );
  };

  const label = progressLabel(progress);
  const detail = progressDetail(progress);
  const isDone = progress?.stage === 'done';
  const isError = progress?.stage === 'error';

  return (
    <div className="flex flex-col bg-white overflow-auto" style={{ maxHeight: '72vh' }}>
      {/* Sheet handle */}
      <div className="flex flex-col items-center pt-2 pb-1 flex-shrink-0">
        <div className="w-10 h-1 rounded-full bg-gray-200 mb-2" />
        <p className="text-xs font-semibold text-gray-500 tracking-wide uppercase">Go</p>
      </div>

      <div className="p-3 space-y-4 overflow-auto">
        {/* Quick nav grid */}
        <div className="grid grid-cols-2 gap-2">
          {LINKS.map((link) => (
            <button
              key={link.url}
              type="button"
              onClick={() => navigateTo(link.url, onClose)}
              className="flex items-start gap-2 p-3 bg-gray-50 border border-gray-100 rounded-xl text-left hover:border-emerald-200 hover:bg-emerald-50 active:scale-95 transition-all group"
            >
              <span className="text-lg leading-none mt-0.5 flex-shrink-0">{link.icon}</span>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-800 group-hover:text-emerald-700">{link.label}</p>
                <p className="text-[10px] text-gray-400 leading-tight mt-0.5">{link.description}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Actions */}
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Actions</p>

          <div className="bg-white border border-gray-100 rounded-xl p-4 space-y-3">
            <div>
              <p className="text-xs font-medium text-gray-800">Import Contracts</p>
              <p className="text-[10px] text-gray-400 mt-0.5 mb-2">
                Navigates to your contracts page, scrapes all pages, and saves them as won jobs.
              </p>

              {/* Progress bar — visible while running */}
              {isRunning && (
                <div className="mb-2 h-1 w-full bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-400 rounded-full animate-pulse"
                    style={{ width: progress?.stage === 'saving' ? '80%' : progress?.stage === 'scraping' ? '50%' : '20%' }}
                  />
                </div>
              )}

              <button
                type="button"
                onClick={handleImportContracts}
                disabled={isRunning}
                className={`w-full py-2 text-xs font-semibold rounded-lg transition-colors ${
                  isDone
                    ? 'bg-emerald-100 text-emerald-700'
                    : isError
                    ? 'bg-red-50 text-red-600 border border-red-200'
                    : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60'
                }`}
              >
                {label}
              </button>
              {detail && (
                <p className={`text-[10px] mt-1.5 text-center ${isDone ? 'text-emerald-600' : 'text-red-500'}`}>
                  {detail}
                </p>
              )}
            </div>
          </div>
        </div>

        <p className="text-[10px] text-gray-300 text-center pb-1">
          Links open in your current Upwork tab
        </p>
      </div>
    </div>
  );
}
