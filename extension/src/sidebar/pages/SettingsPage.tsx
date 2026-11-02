/**
 * Settings: the automatic job scan (stored in the extension) and the job minimums
 * (stored on the profile, used by the server's pre-filter before any job is scored).
 */
import { useEffect, useState } from 'react';
import { apiClient } from '../../lib/api-client';
import {
  INTERVAL_OPTIONS, LOOKBACK_CATCH_UP_UNTIL, LOOKBACK_OPTIONS, PAGE_OPTIONS,
  defaultLookbackDays, type GatherSettings,
} from '../../lib/job-gather';

function send<T>(message: Record<string, unknown>): Promise<T> {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, (r) => resolve(r as T)));
}

function intervalLabel(m: number): string {
  return m < 60 ? `Every ${m} min` : `Every ${m / 60} h`;
}

const catchUpDate = new Date(LOOKBACK_CATCH_UP_UNTIL).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-[11px] font-medium text-gray-700">{label}</p>
        {hint && <p className="text-[10px] text-gray-400 leading-snug">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const selectClass = 'px-2 py-1 text-[11px] border border-gray-200 rounded-lg bg-white';

export default function SettingsPage() {
  const [scan, setScan] = useState<GatherSettings | null>(null);
  const [hourly, setHourly] = useState('');
  const [fixed, setFixed] = useState('');
  const [savedMins, setSavedMins] = useState<{ hourly: string; fixed: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    send<{ settings?: GatherSettings }>({ type: 'GATHER_GET_STATUS' }).then((s) => setScan(s?.settings ?? null));
    apiClient.getProfile()
      .then((p) => {
        const h = p.minimum_hourly_rate != null ? String(Number(p.minimum_hourly_rate)) : '';
        const f = p.minimum_budget != null ? String(Number(p.minimum_budget)) : '';
        setHourly(h); setFixed(f); setSavedMins({ hourly: h, fixed: f });
      })
      .catch(() => setError('Could not load your profile.'));
  }, []);

  const saveScan = async (patch: Partial<GatherSettings>) => {
    const r = await send<{ success: boolean; settings?: GatherSettings }>({ type: 'GATHER_SET_SETTINGS', settings: patch });
    if (r?.success && r.settings) { setScan(r.settings); setNotice('Scan settings saved.'); }
    else setError('Could not save the scan settings.');
  };

  const minsDirty = savedMins && (hourly !== savedMins.hourly || fixed !== savedMins.fixed);
  const saveMins = async () => {
    const h = hourly.trim() === '' ? undefined : Number(hourly);
    const f = fixed.trim() === '' ? undefined : Number(fixed);
    if ((h !== undefined && (!Number.isFinite(h) || h < 0)) || (f !== undefined && (!Number.isFinite(f) || f < 0))) {
      setError('Minimums must be positive numbers.');
      return;
    }
    setSaving(true); setError(null);
    try {
      await apiClient.updateDealbreakers({ minimum_hourly_rate: h, minimum_budget: f });
      setSavedMins({ hourly, fixed });
      setNotice('Minimums saved. New scans skip jobs below them before scoring.');
    } catch {
      setError('Could not save the minimums.');
    } finally {
      setSaving(false);
    }
  };

  const autoDays = defaultLookbackDays();

  return (
    <div className="p-4 space-y-3">
      {notice && <p className="text-[11px] text-emerald-700 bg-emerald-50 px-2 py-1 rounded-lg">{notice}</p>}
      {error && <p className="text-[11px] text-red-600 bg-red-50 px-2 py-1 rounded-lg">{error}</p>}

      <section className="bg-white border border-gray-100 rounded-xl p-3 space-y-3">
        <h2 className="text-[12px] font-semibold text-gray-800">Automatic job scan</h2>
        {!scan ? (
          <p className="text-[11px] text-gray-400">Loading…</p>
        ) : (
          <>
            <Row label="Scheduled scans" hint="Runs only while Chrome is open and you are signed in to Upwork.">
              <label className="flex items-center gap-1.5 text-[11px] text-gray-600 cursor-pointer">
                <input type="checkbox" checked={scan.enabled} onChange={(e) => saveScan({ enabled: e.target.checked })} className="accent-emerald-500" />
                {scan.enabled ? 'On' : 'Off'}
              </label>
            </Row>
            <Row label="How often">
              <select aria-label="Scan interval" value={scan.intervalMinutes} onChange={(e) => saveScan({ intervalMinutes: Number(e.target.value) })} className={selectClass}>
                {INTERVAL_OPTIONS.map((m) => <option key={m} value={m}>{intervalLabel(m)}</option>)}
              </select>
            </Row>
            <Row label="How far back" hint={`Newest first, paging back to this age. Automatic is 14 days until ${catchUpDate}, then 7.`}>
              <select
                aria-label="Lookback window"
                value={scan.lookbackDays ?? 'auto'}
                onChange={(e) => saveScan({ lookbackDays: e.target.value === 'auto' ? null : Number(e.target.value) })}
                className={selectClass}
              >
                <option value="auto">Automatic ({autoDays} days)</option>
                {LOOKBACK_OPTIONS.map((d) => <option key={d} value={d}>{d} days</option>)}
              </select>
            </Row>
            <Row label="Pages per search" hint="Upper limit; a search stops early once it reaches the window or repeats.">
              <select aria-label="Pages per search" value={scan.maxPages} onChange={(e) => saveScan({ maxPages: Number(e.target.value) })} className={selectClass}>
                {PAGE_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Row>
            <Row label="Searches per scan" hint="Searches take turns when you have more than this.">
              <select aria-label="Searches per scan" value={scan.maxQueriesPerRun} onChange={(e) => saveScan({ maxQueriesPerRun: Number(e.target.value) })} className={selectClass}>
                {[5, 10, 15, 20].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Row>
          </>
        )}
      </section>

      <section className="bg-white border border-gray-100 rounded-xl p-3 space-y-3">
        <div>
          <h2 className="text-[12px] font-semibold text-gray-800">Job minimums</h2>
          <p className="text-[10px] text-gray-400 leading-snug">Jobs below these are skipped before scoring. Hourly jobs compare the top of the client's range.</p>
        </div>
        <Row label="Hourly rate at least">
          <div className="flex items-center gap-1 text-[11px] text-gray-500">
            $<input aria-label="Minimum hourly rate" inputMode="decimal" value={hourly} onChange={(e) => setHourly(e.target.value)}
              className="w-16 px-2 py-1 border border-gray-200 rounded-lg text-right tabular-nums" />/hr
          </div>
        </Row>
        <Row label="Fixed price at least">
          <div className="flex items-center gap-1 text-[11px] text-gray-500">
            $<input aria-label="Minimum fixed budget" inputMode="decimal" value={fixed} onChange={(e) => setFixed(e.target.value)}
              className="w-20 px-2 py-1 border border-gray-200 rounded-lg text-right tabular-nums" />
          </div>
        </Row>
        <button
          type="button"
          onClick={saveMins}
          disabled={!minsDirty || saving}
          className="w-full py-1.5 text-[11px] font-medium bg-emerald-600 text-white rounded-lg disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save minimums'}
        </button>
      </section>
    </div>
  );
}
