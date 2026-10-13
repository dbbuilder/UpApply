import { useEffect, useMemo, useState } from 'react';
import { apiClient, Fact, FactKind, FactStatus } from '../../lib/api-client';

const KIND_LABELS: Record<FactKind, string> = {
  metric: 'Metrics',
  outcome: 'Outcomes',
  project: 'Projects',
  client_quote: 'Client quotes',
  credential: 'Credentials',
  role: 'Roles',
  tech: 'Tech',
};
const KIND_ORDER: FactKind[] = ['metric', 'outcome', 'project', 'client_quote', 'credential', 'role', 'tech'];
const STATUS_TABS: FactStatus[] = ['candidate', 'approved', 'rejected'];
const STATUS_LABELS: Record<FactStatus, string> = { candidate: 'To review', approved: 'Approved', rejected: 'Rejected' };

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export default function FactsPage() {
  const [status, setStatus] = useState<FactStatus>('candidate');
  const [facts, setFacts] = useState<Fact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackContract, setFeedbackContract] = useState('');

  const load = async (s: FactStatus) => {
    setLoading(true);
    setError(null);
    setSelected(new Set());
    try {
      setFacts(await apiClient.getFacts(s));
    } catch (err) {
      setError(errorText(err, 'Failed to load facts.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(status);
  }, [status]);

  const groups = useMemo(
    () => KIND_ORDER
      .map(kind => ({ kind, items: facts.filter(f => f.kind === kind) }))
      .filter(g => g.items.length > 0),
    [facts],
  );

  const setFactStatus = async (fact: Fact, next: FactStatus) => {
    try {
      await apiClient.updateFact(fact.id, { status: next });
      setFacts(prev => prev.filter(f => f.id !== fact.id));
    } catch (err) {
      setError(errorText(err, 'Update failed.'));
    }
  };

  const saveEdit = async (fact: Fact) => {
    const statement = draft.trim();
    if (!statement) return;
    try {
      const updated = await apiClient.updateFact(fact.id, { statement });
      setFacts(prev => prev.map(f => (f.id === fact.id ? updated : f)));
      setEditingId(null);
    } catch (err) {
      setError(errorText(err, 'Save failed.'));
    }
  };

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (items: Fact[]) => {
    setSelected(prev => {
      const next = new Set(prev);
      const allSelected = items.every(f => next.has(f.id));
      items.forEach(f => (allSelected ? next.delete(f.id) : next.add(f.id)));
      return next;
    });
  };

  const bulkApprove = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    try {
      const result = await apiClient.bulkApproveFacts(ids);
      setFacts(prev => prev.filter(f => !selected.has(f.id)));
      setSelected(new Set());
      setNotice(`Approved ${result.approved} facts.`);
    } catch (err) {
      setError(errorText(err, 'Bulk approve failed.'));
    }
  };

  const runExtraction = async (from: 'memories' | 'proposals' | 'contracts') => {
    setBusy(true);
    setError(null);
    setNotice(
      from === 'memories' ? 'Extracting facts from bio memories…'
        : from === 'proposals' ? 'Extracting facts from Upwork proposals…'
        : 'Extracting facts from Upwork contracts…',
    );
    try {
      const r = from === 'memories' ? await apiClient.factsFromMemories()
        : from === 'proposals' ? await apiClient.factsFromProposals(10)
        : await apiClient.factsFromContracts();
      setNotice(
        `${r.created} new · ${r.merged} merged · ${r.auto_approved} auto-approved · ${r.skipped} already done` +
        (r.failed ? ` · ${r.failed} failed` : '') +
        (r.remaining ? ` · ${r.remaining} left, run again` : ''),
      );
      await load(status);
    } catch (err) {
      setError(errorText(err, 'Extraction failed.'));
      setNotice(null);
    } finally {
      setBusy(false);
    }
  };

  const submitFeedback = async () => {
    const text = feedbackText.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const r = await apiClient.ingestFacts('client_feedback', [
        { text, context: feedbackContract.trim() ? `Contract: ${feedbackContract.trim()}` : undefined },
      ]);
      setNotice(`${r.created} new · ${r.merged} merged · ${r.auto_approved} auto-approved from client feedback`);
      setFeedbackText('');
      setFeedbackContract('');
      await load(status);
    } catch (err) {
      setError(errorText(err, 'Could not extract facts from that feedback.'));
    } finally {
      setBusy(false);
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

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('memories')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From bio memories
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('proposals')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From Upwork proposals
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => runExtraction('contracts')}
          className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white hover:border-emerald-300 disabled:opacity-50"
        >
          From Upwork contracts
        </button>
        {status === 'candidate' && selected.size > 0 && (
          <button
            type="button"
            onClick={bulkApprove}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
          >
            Approve {selected.size} selected
          </button>
        )}
      </div>

      <details className="bg-white border border-gray-100 rounded-xl p-3">
        <summary className="text-xs font-medium text-gray-700 cursor-pointer">Add client feedback</summary>
        <div className="mt-2 space-y-2">
          <input
            type="text"
            value={feedbackContract}
            onChange={e => setFeedbackContract(e.target.value)}
            placeholder="Contract title (optional)"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5"
          />
          <textarea
            value={feedbackText}
            onChange={e => setFeedbackText(e.target.value)}
            rows={4}
            placeholder="Paste the client's feedback from Upwork"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5"
          />
          <button
            type="button"
            disabled={busy || !feedbackText.trim()}
            onClick={submitFeedback}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Extract facts
          </button>
        </div>
      </details>

      {notice && <p className="text-xs text-gray-600 bg-gray-100 rounded-lg px-3 py-2">{notice}</p>}
      {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      {loading && <p className="text-xs text-gray-400">Loading facts…</p>}
      {!loading && facts.length === 0 && (
        <p className="text-xs text-gray-400">No {STATUS_LABELS[status].toLowerCase()} facts.</p>
      )}

      {groups.map(({ kind, items }) => (
        <section key={kind} className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">
              {KIND_LABELS[kind]} ({items.length})
            </h3>
            {status === 'candidate' && (
              <button type="button" onClick={() => toggleGroup(items)} className="text-[11px] text-emerald-700 hover:underline">
                {items.every(f => selected.has(f.id)) ? 'Clear' : 'Select all'}
              </button>
            )}
          </div>

          {items.map(fact => {
            const source = fact.sources[0];
            return (
              <div key={fact.id} className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
                <div className="flex items-start gap-2">
                  {status === 'candidate' && (
                    <input
                      type="checkbox"
                      checked={selected.has(fact.id)}
                      onChange={() => toggle(fact.id)}
                      className="mt-1 accent-emerald-600"
                    />
                  )}
                  {editingId === fact.id ? (
                    <textarea
                      value={draft}
                      onChange={e => setDraft(e.target.value)}
                      rows={3}
                      className="flex-1 text-sm border border-gray-200 rounded-lg p-2"
                    />
                  ) : (
                    <p className="flex-1 text-sm text-gray-800">{fact.statement}</p>
                  )}
                  <span className="text-[10px] text-gray-400 tabular-nums">{fact.strength.toFixed(1)}</span>
                </div>

                {source?.snippet && (
                  <p className="text-[11px] text-gray-500 italic border-l-2 border-gray-200 pl-2">
                    “{source.snippet}”
                  </p>
                )}
                <p className="text-[10px] text-gray-400">
                  {source?.source_type ?? fact.source_type}
                  {fact.sources.length > 1 ? ` · ${fact.sources.length} sources` : ''}
                  {fact.job_types.length ? ` · ${fact.job_types.join(', ')}` : ''}
                </p>

                <div className="flex gap-2">
                  {editingId === fact.id ? (
                    <>
                      <button type="button" onClick={() => saveEdit(fact)} className="text-xs text-emerald-700 font-medium">Save</button>
                      <button type="button" onClick={() => setEditingId(null)} className="text-xs text-gray-500">Cancel</button>
                    </>
                  ) : (
                    <>
                      {status !== 'approved' && (
                        <button type="button" onClick={() => setFactStatus(fact, 'approved')} className="text-xs text-emerald-700 font-medium">
                          Approve
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => { setEditingId(fact.id); setDraft(fact.statement); }}
                        className="text-xs text-gray-600"
                      >
                        Edit
                      </button>
                      {status !== 'rejected' && (
                        <button type="button" onClick={() => setFactStatus(fact, 'rejected')} className="text-xs text-red-600">
                          Reject
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}
