/**
 * GoPage — quick navigation to Upwork pages + one-click actions from the sidebar.
 */
import { useState } from 'react';

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

function navigateTo(url: string) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0]?.id;
    if (tabId) chrome.tabs.update(tabId, { url });
  });
}

type ImportStatus = 'idle' | 'navigating' | 'importing' | 'done' | 'error';

export default function GoPage() {
  const [importStatus, setImportStatus] = useState<ImportStatus>('idle');
  const [importResult, setImportResult] = useState<string | null>(null);

  const handleImportContracts = () => {
    setImportStatus('navigating');
    setImportResult(null);

    chrome.runtime.sendMessage(
      { type: 'NAVIGATE_AND_IMPORT_CONTRACTS' },
      (resp: { success: boolean; imported?: number; updated?: number; total?: number; error?: string } | undefined) => {
        if (chrome.runtime.lastError || !resp) {
          setImportStatus('error');
          setImportResult(chrome.runtime.lastError?.message || 'No response from background');
          return;
        }
        if (resp.success) {
          const n = (resp.imported ?? 0) + (resp.updated ?? 0);
          setImportStatus('done');
          setImportResult(`${n} contract${n !== 1 ? 's' : ''} synced (${resp.imported ?? 0} new, ${resp.updated ?? 0} updated)`);
        } else {
          setImportStatus('error');
          setImportResult(resp.error || 'Import failed');
        }
      }
    );

    // Show "importing" label once navigating has started
    setTimeout(() => {
      setImportStatus((s) => s === 'navigating' ? 'importing' : s);
    }, 2000);
  };

  const importLabel = {
    idle:       '📥 Import Contracts',
    navigating: 'Opening contracts page…',
    importing:  'Importing…',
    done:       '✓ Done',
    error:      '✗ Failed — retry?',
  }[importStatus];

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="bg-white border-b px-4 pt-3 pb-3 flex-shrink-0">
        <h1 className="font-bold text-gray-900 text-sm">Go</h1>
        <p className="text-xs text-gray-400 mt-0.5">Open Upwork pages in your active tab</p>
      </div>

      <div className="p-4 space-y-5">
        {/* Quick nav grid */}
        <div className="grid grid-cols-2 gap-2">
          {LINKS.map((link) => (
            <button
              key={link.url}
              type="button"
              onClick={() => navigateTo(link.url)}
              className="flex items-start gap-2 p-3 bg-white border border-gray-100 rounded-xl text-left hover:border-emerald-200 hover:bg-emerald-50 transition-colors group"
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
                Navigates to your contracts page, scrapes all contracts, and saves them as won jobs.
              </p>
              <button
                type="button"
                onClick={handleImportContracts}
                disabled={importStatus === 'navigating' || importStatus === 'importing'}
                className={`w-full py-2 text-xs font-semibold rounded-lg transition-colors ${
                  importStatus === 'done'
                    ? 'bg-emerald-100 text-emerald-700'
                    : importStatus === 'error'
                    ? 'bg-red-50 text-red-600 border border-red-200'
                    : 'bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60'
                }`}
              >
                {importLabel}
              </button>
              {importResult && (
                <p className={`text-[10px] mt-1.5 text-center ${importStatus === 'done' ? 'text-emerald-600' : 'text-red-500'}`}>
                  {importResult}
                </p>
              )}
            </div>
          </div>
        </div>

        <p className="text-[10px] text-gray-300 text-center">
          Links open in your current Upwork tab
        </p>
      </div>
    </div>
  );
}
