/**
 * GoPage — quick navigation to Upwork pages from the sidebar.
 * Import actions have moved to the Data tab (Data → Import).
 */

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
  if (onDone) setTimeout(onDone, 380);
}

interface GoPageProps {
  onClose?: () => void;
}

export default function GoPage({ onClose }: GoPageProps) {
  return (
    <div className="flex flex-col bg-white overflow-auto" style={{ maxHeight: '72vh' }}>
      {/* Sheet handle */}
      <div className="flex flex-col items-center pt-2 pb-1 flex-shrink-0">
        <div className="w-10 h-1 rounded-full bg-gray-200 mb-2" />
        <p className="text-xs font-semibold text-gray-500 tracking-wide uppercase">Go</p>
      </div>

      <div className="p-3 pb-4 space-y-2 overflow-auto">
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

        <p className="text-[10px] text-gray-300 text-center pt-1">
          Links open in your current Upwork tab · Imports are in the Data tab
        </p>
      </div>
    </div>
  );
}
