/**
 * GuardrailSettings — configure autonomous agent limits.
 *
 * Let users set:
 * - Master on/off switch
 * - Daily proposal cap
 * - Min connects reserve
 * - Max bid (hourly + fixed)
 * - Min score threshold
 * - Quiet hours (pause window)
 * - Connects balance (manual entry until Upwork API available)
 */
import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError, GuardrailConfig } from '../../lib/api-client';
import { useAppStore } from '../store';

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      <label className="text-[11px] font-medium text-gray-700 block">{label}</label>
      {hint && <p className="text-[9px] text-gray-400 leading-snug">{hint}</p>}
      <div className="mt-0.5">{children}</div>
    </div>
  );
}

function NumericInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  placeholder,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
}) {
  return (
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={value ?? ''}
      placeholder={placeholder}
      onChange={(e) => {
        const v = e.target.value;
        onChange(v === '' ? null : parseFloat(v));
      }}
      className="w-full px-2.5 py-1.5 text-[11px] border border-gray-200 rounded-lg
        focus:outline-none focus:border-indigo-300 bg-gray-50"
    />
  );
}

export default function GuardrailSettings() {
  const { setCurrentView } = useAppStore();
  const [cfg, setCfg] = useState<GuardrailConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await apiClient.getGuardrails();
      setCfg(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load guardrails.');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    if (!cfg) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await apiClient.updateGuardrails({
        ...cfg,
        connects_balance: cfg.connects_balance ?? undefined,
      });
      setCfg(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) {
    return (
      <div className="p-4 text-[11px] text-gray-400 animate-pulse">Loading guardrails…</div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentView('suggestions')}
            className="text-[11px] text-gray-400 hover:text-gray-600 -ml-1 px-1.5 py-1 rounded-lg hover:bg-gray-100 transition-colors"
          >
            ← Back
          </button>
          <h2 className="text-sm font-semibold text-gray-800">Guardrail Settings</h2>
        </div>
        <span className="text-[9px] text-gray-400">Agent safety limits</span>
      </div>

      {/* Master switch */}
      <div className="flex items-center justify-between bg-gray-50 border border-gray-100 rounded-xl px-3 py-2.5">
        <div>
          <p className="text-[11px] font-medium text-gray-700">Agent enabled</p>
          <p className="text-[9px] text-gray-400">Turn off to pause all autonomous actions</p>
        </div>
        <button
          type="button"
          onClick={() => setCfg({ ...cfg, enabled: !cfg.enabled })}
          className={`relative w-9 h-5 rounded-full transition-colors ${
            cfg.enabled ? 'bg-emerald-400' : 'bg-gray-300'
          }`}
        >
          <span
            className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
              cfg.enabled ? 'translate-x-4' : ''
            }`}
          />
        </button>
      </div>

      {/* Proposal limits */}
      <div className="space-y-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Proposal Limits</p>

        <Field label="Max proposals per day" hint="Hard cap — agent stops after this many daily submissions">
          <NumericInput
            value={cfg.max_proposals_per_day}
            onChange={(v) => setCfg({ ...cfg, max_proposals_per_day: v ?? 5 })}
            min={1}
            max={50}
          />
        </Field>

        <Field label="Min score threshold" hint="Jobs below this score won't be autonomously prepped">
          <div className="flex items-center gap-2">
            <NumericInput
              value={cfg.min_score_threshold}
              onChange={(v) => setCfg({ ...cfg, min_score_threshold: v ?? 60 })}
              min={0}
              max={100}
              step={0.5}
            />
            <span className="text-[10px] text-gray-400 flex-shrink-0">/ 100</span>
          </div>
        </Field>

        <Field label="Max bid — hourly ($)" hint="Reject any job requiring a bid above this rate">
          <NumericInput
            value={cfg.max_bid_hourly}
            onChange={(v) => setCfg({ ...cfg, max_bid_hourly: v })}
            min={0}
            step={5}
            placeholder="No limit"
          />
        </Field>

        <Field label="Max bid — fixed ($)" hint="Reject any fixed-price job above this amount">
          <NumericInput
            value={cfg.max_bid_fixed}
            onChange={(v) => setCfg({ ...cfg, max_bid_fixed: v })}
            min={0}
            step={50}
            placeholder="No limit"
          />
        </Field>
      </div>

      {/* Connects */}
      <div className="space-y-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Connects</p>

        <Field label="Current balance" hint="Enter your current Upwork connects balance">
          <NumericInput
            value={cfg.connects_balance}
            onChange={(v) => setCfg({ ...cfg, connects_balance: v ?? null })}
            min={0}
            placeholder="e.g. 80"
          />
        </Field>

        <Field label="Minimum reserve" hint="Agent stops submitting when balance falls below this">
          <NumericInput
            value={cfg.min_connects_reserve}
            onChange={(v) => setCfg({ ...cfg, min_connects_reserve: v ?? 20 })}
            min={0}
          />
        </Field>
      </div>

      {/* Quiet hours */}
      <div className="space-y-3">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">Quiet Hours (UTC)</p>
        <p className="text-[9px] text-gray-400 -mt-2">Leave blank to disable quiet hours</p>

        <div className="flex gap-2">
          <Field label="Start hour (0–23)">
            <NumericInput
              value={cfg.pause_start_hour}
              onChange={(v) => setCfg({ ...cfg, pause_start_hour: v })}
              min={0}
              max={23}
              placeholder="e.g. 22"
            />
          </Field>
          <Field label="End hour (0–23)">
            <NumericInput
              value={cfg.pause_end_hour}
              onChange={(v) => setCfg({ ...cfg, pause_end_hour: v })}
              min={0}
              max={23}
              placeholder="e.g. 8"
            />
          </Field>
        </div>
      </div>

      {/* Error / saved */}
      {error && (
        <p className="text-[10px] text-red-500 bg-red-50 px-2 py-1 rounded-lg">{error}</p>
      )}
      {saved && (
        <p className="text-[10px] text-emerald-600 bg-emerald-50 px-2 py-1 rounded-lg">
          Guardrails saved.
        </p>
      )}

      <button
        type="button"
        disabled={saving}
        onClick={handleSave}
        className="w-full py-2 text-[12px] font-medium bg-indigo-500 text-white rounded-xl
          hover:bg-indigo-600 active:scale-[0.98] transition-all disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save Guardrails'}
      </button>
    </div>
  );
}
