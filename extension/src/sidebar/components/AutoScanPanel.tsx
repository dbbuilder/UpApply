/**
 * AutoScanPanel — settings and status for the automatic job scan (background/gatherer.ts).
 * Off until the user turns it on.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { INTERVAL_OPTIONS } from '../../lib/job-gather';
import type { GatherLastRun, GatherRunProgress, GatherSettings } from '../../lib/job-gather';

interface GatherStatusResponse {
  success: boolean;
  settings?: GatherSettings;
  lastRun?: GatherLastRun | null;
  running?: GatherRunProgress | null;
  backoffUntil?: number | null;
  error?: string;
}

const WATCHED_KEYS = ['gatherSettings', 'gatherRun', 'gatherLastRun', 'gatherBackoff'];

function send<T>(message: Record<string, unknown>): Promise<T> {
  return new Promise((resolve) => chrome.runtime.sendMessage(message, (r) => resolve(r as T)));
}

function intervalLabel(min: number): string {
  return min % 60 === 0 ? `Every ${min / 60} h` : `Every ${min} min`;
}

function timeAgo(iso: string): string {
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (min < 1) return 'just now';
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

interface AutoScanPanelProps {
  /** Called when a run finishes with new suggestions, so the queue list can reload. */
  onNewSuggestions: () => void;
}

export default function AutoScanPanel({ onNewSuggestions }: AutoScanPanelProps) {
  const [status, setStatus] = useState<GatherStatusResponse | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const lastFinished = useRef<string | null>(null);
  const onNewRef = useRef(onNewSuggestions);
  onNewRef.current = onNewSuggestions;

  const refresh = useCallback(async () => {
    const s = await send<GatherStatusResponse>({ type: 'GATHER_GET_STATUS' });
    if (!s?.success) return;
    setStatus(s);
    const finished = s.lastRun?.finished_at ?? null;
    // A run that finished while the panel was open and queued new suggestions: reload the queue.
    if (lastFinished.current !== null && finished && finished !== lastFinished.current && (s.lastRun?.suggested ?? 0) > 0) {
      onNewRef.current();
    }
    lastFinished.current = finished ?? '';
  }, []);

  useEffect(() => {
    refresh();
    const listener = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area === 'local' && WATCHED_KEYS.some((k) => k in changes)) refresh();
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, [refresh]);

  const save = async (patch: Partial<GatherSettings>) => {
    setSaving(true);
    await send({ type: 'GATHER_SET_SETTINGS', settings: patch });
    await refresh();
    setSaving(false);
  };

  const runNow = async () => {
    setNotice(null);
    const r = await send<{ success: boolean; reason?: string }>({ type: 'GATHER_RUN_NOW' });
    if (!r?.success) setNotice(r?.reason || 'Could not start the scan.');
    await refresh();
  };

  if (!status?.settings) return null;
  const { settings, lastRun, running, backoffUntil } = status;

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-gray-700">Automatic job scan</span>
        <label className="flex items-center gap-1.5 text-[10px] text-gray-500 cursor-pointer">
          <input
            type="checkbox"
            checked={settings.enabled}
            disabled={saving}
            onChange={(e) => save({ enabled: e.target.checked })}
            className="accent-emerald-500"
          />
          {settings.enabled ? 'On' : 'Off'}
        </label>
      </div>

      <div className="flex items-center gap-2">
        <select
          value={settings.intervalMinutes}
          disabled={saving}
          onChange={(e) => save({ intervalMinutes: Number(e.target.value) })}
          aria-label="Scan interval"
          className="flex-1 px-2 py-1 text-[11px] border border-gray-200 rounded-lg bg-white"
        >
          {INTERVAL_OPTIONS.map((m) => (
            <option key={m} value={m}>{intervalLabel(m)}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={runNow}
          disabled={!!running}
          className="shrink-0 whitespace-nowrap tabular-nums px-3 py-1 text-[11px] font-medium bg-emerald-50 text-emerald-700 rounded-lg
            hover:bg-emerald-100 active:scale-95 transition-all disabled:opacity-50"
        >
          {running ? `Scanning ${Math.min(running.index + 1, running.queries.length)} of ${running.queries.length}` : 'Run now'}
        </button>
      </div>

      {lastRun && (
        <p className="text-[10px] text-gray-500 leading-snug">
          Last scan {timeAgo(lastRun.finished_at)}: {lastRun.queries_run} quer{lastRun.queries_run === 1 ? 'y' : 'ies'},{' '}
          {lastRun.jobs_sent} jobs sent, {lastRun.suggested} new suggestion{lastRun.suggested === 1 ? '' : 's'},{' '}
          {lastRun.duplicates} already seen, {lastRun.pre_filtered} pre-filtered.
        </p>
      )}
      {lastRun?.error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-lg leading-snug">{lastRun.error}</p>
      )}
      {backoffUntil && settings.enabled && (
        <p className="text-[10px] text-amber-600 bg-amber-50 px-2 py-1 rounded-lg leading-snug">
          Scheduled scans paused until {new Date(backoffUntil).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}.
        </p>
      )}
      {notice && <p className="text-[10px] text-amber-600 leading-snug">{notice}</p>}

      <p className="text-[9px] text-gray-400 leading-snug">
        {settings.enabled ? '' : 'Off by default. '}
        Runs your active search queries (up to {settings.maxQueriesPerRun} per scan, taking turns) in a hidden tab,
        only while Chrome is open and you are signed in to Upwork and UpApply.
      </p>
    </div>
  );
}
