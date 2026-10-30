import { useEffect, useState } from 'react';
import { apiClient, LearnedRule, LearnedRuleStatus } from '../../lib/api-client';

const STATUS_TABS: LearnedRuleStatus[] = ['proposed', 'accepted', 'rejected'];
const STATUS_LABELS: Record<LearnedRuleStatus, string> = {
  proposed: 'To review',
  accepted: 'Accepted',
  rejected: 'Rejected',
};

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function RulesPage() {
  const [status, setStatus] = useState<LearnedRuleStatus>('proposed');
  const [rules, setRules] = useState<LearnedRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async (s: LearnedRuleStatus) => {
    setLoading(true);
    setError(null);
    try {
      setRules(await apiClient.getLearnedRules(s));
    } catch (err) {
      setError(errorText(err, 'Failed to load rules.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(status);
  }, [status]);

  const suggest = async () => {
    setBusy(true);
    setError(null);
    setNotice('Reading your edits…');
    try {
      const r = await apiClient.proposeLearnedRules();
      setNotice(
        r.pairs_found + r.refine_requests_found === 0
          ? 'No edited letters or refine requests yet. Edit and submit a few drafts first.'
          : `${r.proposed.length} new rule${r.proposed.length === 1 ? '' : 's'} from ` +
            `${r.pairs_found} edited letter${r.pairs_found === 1 ? '' : 's'} and ` +
            `${r.refine_requests_found} refine request${r.refine_requests_found === 1 ? '' : 's'}.`,
      );
      if (status === 'proposed') await load('proposed');
      else setStatus('proposed');
    } catch (err) {
      setError(errorText(err, 'Could not suggest rules.'));
      setNotice(null);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (rule: LearnedRule, next: 'accepted' | 'rejected') => {
    setError(null);
    try {
      const r = await apiClient.decideLearnedRule(rule.id, next);
      setRules(prev => prev.filter(x => x.id !== rule.id));
      setNotice(r.note ?? (next === 'accepted' ? 'Rule accepted. New drafts will follow it.' : 'Rule rejected.'));
    } catch (err) {
      setError(errorText(err, 'Update failed.'));
    }
  };

  return (
    <div className="p-4 space-y-3">
      <div className="flex gap-1">
        {STATUS_TABS.map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              status === s ? 'bg-emerald-100 text-emerald-700' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
          >
            {STATUS_LABELS[s]}
          </button>
        ))}
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={suggest}
        className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
      >
        Suggest rules from my edits
      </button>

      {notice && <p className="text-xs text-gray-600 bg-gray-100 rounded-lg px-3 py-2">{notice}</p>}
      {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      {loading && <p className="text-xs text-gray-400">Loading rules…</p>}
      {!loading && rules.length === 0 && (
        <p className="text-xs text-gray-400">No {STATUS_LABELS[status].toLowerCase()} rules.</p>
      )}

      {rules.map(rule => (
        <div key={rule.id} className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
          <div className="flex items-start gap-2">
            <p className="flex-1 text-sm text-gray-800">{rule.rule}</p>
            <span className="text-[10px] text-gray-400 tabular-nums">×{rule.times_seen}</span>
          </div>
          <p className="text-[11px] text-gray-500 italic border-l-2 border-gray-200 pl-2">“{rule.evidence_quote}”</p>
          {rule.status === 'proposed' && (
            <div className="flex gap-2">
              <button type="button" onClick={() => decide(rule, 'accepted')} className="text-xs text-emerald-700 font-medium">
                Accept
              </button>
              <button type="button" onClick={() => decide(rule, 'rejected')} className="text-xs text-red-600">
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
