import { useState, useEffect } from 'react';
import { apiClient, ProposalStats, ApplicationStats } from '../../lib/api-client';
import ImportsTab from './ImportsTab';

type DataTab = 'data' | 'import';

// ── Data overview ─────────────────────────────────────────────────────────────

interface DataSummary {
  proposals: ProposalStats | null;
  applications: ApplicationStats | null;
  memoriesCount: number | null;
  coverLettersCount: number | null;
  jobsCount: number | null;
  searchQueriesCount: number | null;
}

function Stat({ label, value, sub, color = 'text-gray-900' }: {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}) {
  return (
    <div className="bg-gray-50 rounded-lg p-2.5 text-center">
      <div className={`text-lg font-bold leading-none ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-500 mt-0.5 leading-tight">{label}</div>
      {sub && <div className="text-[9px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function DataTab() {
  const [summary, setSummary] = useState<DataSummary>({
    proposals: null, applications: null, memoriesCount: null,
    coverLettersCount: null, jobsCount: null, searchQueriesCount: null,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      apiClient.getProposalStats(),
      apiClient.getApplicationStats(),
      apiClient.getMemories(),
      apiClient.getCoverLetters(),
      apiClient.getJobs(),
      apiClient.getSearchQueries(),
    ]).then(([props, apps, mems, letters, jobs, searches]) => {
      if (cancelled) return;
      setSummary({
        proposals: props.status === 'fulfilled' ? props.value : null,
        applications: apps.status === 'fulfilled' ? apps.value : null,
        memoriesCount: mems.status === 'fulfilled' ? mems.value.length : null,
        coverLettersCount: letters.status === 'fulfilled' ? letters.value.length : null,
        jobsCount: jobs.status === 'fulfilled' ? jobs.value.length : null,
        searchQueriesCount: searches.status === 'fulfilled' ? searches.value.length : null,
      });
      setLoading(false);
    }).catch(() => {
      if (!cancelled) { setError('Failed to load data summary.'); setLoading(false); }
    });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div className="p-4 text-sm text-gray-400 text-center pt-8">Loading data summary…</div>;
  if (error) return <div className="p-4 text-sm text-red-500 text-center">{error}</div>;

  const { proposals: p, applications: a } = summary;

  return (
    <div className="p-4 space-y-4">
      {/* Corpus counts */}
      <div>
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">Corpus</p>
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Proposals" value={p?.total_proposals ?? '—'} />
          <Stat label="Memories" value={summary.memoriesCount ?? '—'} />
          <Stat label="Cover Letters" value={summary.coverLettersCount ?? '—'} />
          <Stat label="Jobs Scored" value={p?.scored_count ?? '—'} />
          <Stat label="Searches" value={summary.searchQueriesCount ?? '—'} />
          <Stat label="All Jobs" value={summary.jobsCount ?? '—'} />
        </div>
      </div>

      {/* Proposal funnel */}
      {p && p.total_proposals > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">Proposal Funnel</p>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Submitted" value={p.total_proposals} />
            <Stat label="Responded" value={p.responded} sub={`${p.response_rate.toFixed(0)}% rate`} color="text-amber-600" />
            <Stat label="Hired" value={p.hired} sub={`${p.hire_rate.toFixed(0)}% rate`} color="text-emerald-600" />
          </div>
          {p.total_earnings > 0 && (
            <div className="mt-2 bg-emerald-50 rounded-lg p-2.5 text-center">
              <span className="text-xs text-emerald-600 font-medium">
                Tracked earnings: ${p.total_earnings.toLocaleString()}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Applications (tracked separately from proposals) */}
      {a && a.total_applications > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-2">Applications (Tracked)</p>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Total" value={a.total_applications} />
            <Stat label="Responded" value={a.responded} sub={`${a.response_rate.toFixed(0)}%`} color="text-amber-600" />
            <Stat label="Hired" value={a.hired} sub={`${a.success_rate.toFixed(0)}%`} color="text-emerald-600" />
          </div>
        </div>
      )}

      {p?.total_proposals === 0 && (!a || a.total_applications === 0) && (
        <div className="text-center py-6 text-gray-400 text-xs">
          No data yet — use the Import tab to seed your corpus.
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ImportPage() {
  const [activeTab, setActiveTab] = useState<DataTab>('data');

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 pt-3 flex-shrink-0">
        <h1 className="font-bold text-gray-900 text-sm mb-2">Data</h1>
        <div className="flex gap-1 pb-2">
          {([
            { id: 'data' as const, label: 'Overview' },
            { id: 'import' as const, label: '↓ Import' },
          ]).map(tab => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {activeTab === 'data' && <DataTab />}
        {activeTab === 'import' && <ImportsTab />}
      </div>
    </div>
  );
}
