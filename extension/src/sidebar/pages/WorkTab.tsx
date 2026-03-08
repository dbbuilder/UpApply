/**
 * WorkTab — log time and tasks against active Upwork contracts.
 *
 * Modes:
 *   timer   → Start/Stop live timer, auto-fills duration
 *   manual  → Pick start datetime + end datetime
 *   quick   → Enter hours directly (e.g. 2.5)
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { apiClient, Job, WorkLog, WorkLogListResponse } from '../../lib/api-client';

type TimeMode = 'timer' | 'manual' | 'quick';

function formatMinutes(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
}

// ── Attachment picker ────────────────────────────────────────────────────────

interface AttachmentState {
  filename: string;
  text: string;
  preview?: string;   // data URL for images
  extracting: boolean;
}

function AttachmentPicker({
  value,
  onChange,
}: {
  value: AttachmentState | null;
  onChange: (v: AttachmentState | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    const isImage = file.type.startsWith('image/');
    const isText = file.type.startsWith('text/') || file.name.endsWith('.md') || file.name.endsWith('.txt');

    if (isText) {
      const text = await file.text();
      onChange({ filename: file.name, text, extracting: false });
      return;
    }

    if (isImage) {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const dataUrl = e.target?.result as string;
        onChange({ filename: file.name, text: '', preview: dataUrl, extracting: true });
        try {
          const result = await apiClient.extractWorkImage(dataUrl, file.name);
          onChange({
            filename: file.name,
            text: result.extracted_text
              ? `${result.summary}\n\n${result.extracted_text}`
              : result.summary,
            preview: dataUrl,
            extracting: false,
          });
        } catch {
          onChange({ filename: file.name, text: `[Image: ${file.name}]`, preview: dataUrl, extracting: false });
        }
      };
      reader.readAsDataURL(file);
      return;
    }

    // PDF / other: just store filename
    onChange({ filename: file.name, text: `[Attachment: ${file.name}]`, extracting: false });
  };

  return (
    <div>
      <label className="block text-xs text-gray-500 mb-1">Attachment (optional)</label>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="text-xs px-2 py-1 border border-gray-200 rounded hover:bg-gray-50 text-gray-600"
        >
          📎 {value ? 'Change file' : 'Attach file'}
        </button>
        {value && (
          <span className="text-xs text-gray-500 truncate max-w-[120px]">{value.filename}</span>
        )}
        {value && (
          <button type="button" onClick={() => onChange(null)} className="text-xs text-red-400 hover:text-red-600">
            ✕
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,.txt,.md,.pdf,.docx"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) handleFile(f);
          e.target.value = '';
        }}
      />
      {value?.extracting && (
        <p className="text-[10px] text-gray-400 mt-1">Extracting text from image…</p>
      )}
      {value?.preview && (
        <img src={value.preview} alt="attachment" className="mt-2 max-h-24 rounded border border-gray-100 object-contain" />
      )}
    </div>
  );
}

// ── Work log entry card ───────────────────────────────────────────────────────

function LogCard({ log, onDelete }: { log: WorkLog; onDelete: (id: string) => void }) {
  const date = new Date(log.created_at);
  const dateStr = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="bg-white rounded-lg border border-gray-100 p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-800 line-clamp-2">{log.task_description}</p>
          {log.notes && <p className="text-[10px] text-gray-400 mt-0.5 line-clamp-1">{log.notes}</p>}
        </div>
        <button
          type="button"
          onClick={() => onDelete(log.id)}
          className="text-gray-300 hover:text-red-400 flex-shrink-0 text-xs leading-none"
          title="Delete"
        >
          ✕
        </button>
      </div>
      <div className="flex items-center gap-3 text-[10px] text-gray-400">
        <span>{dateStr} {timeStr}</span>
        {log.duration_minutes != null && (
          <span className="font-medium text-emerald-600">{formatMinutes(log.duration_minutes)}</span>
        )}
        {log.attachment_filename && (
          <span>📎 {log.attachment_filename}</span>
        )}
      </div>
    </div>
  );
}

// ── Main WorkTab ──────────────────────────────────────────────────────────────

export default function WorkTab() {
  // Contract list
  const [contracts, setContracts] = useState<Job[]>([]);
  const [contractsLoading, setContractsLoading] = useState(true);
  const [selectedJobId, setSelectedJobId] = useState<string>('');

  // Form state
  const [timeMode, setTimeMode] = useState<TimeMode>('timer');
  const [taskDescription, setTaskDescription] = useState('');
  const [notes, setNotes] = useState('');
  const [attachment, setAttachment] = useState<AttachmentState | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Timer mode
  const [timerRunning, setTimerRunning] = useState(false);
  const [timerStart, setTimerStart] = useState<Date | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Manual mode
  const [manualStart, setManualStart] = useState('');
  const [manualEnd, setManualEnd] = useState('');

  // Quick mode
  const [quickHours, setQuickHours] = useState('');

  // Work log history
  const [logData, setLogData] = useState<WorkLogListResponse | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);

  // Load contracts once
  useEffect(() => {
    apiClient.getActiveContracts()
      .then((jobs) => {
        setContracts(jobs);
        if (jobs.length === 1) setSelectedJobId(jobs[0].id);
      })
      .catch(() => {})
      .finally(() => setContractsLoading(false));
  }, []);

  // Load logs when contract changes
  const loadLogs = useCallback(async (jobId: string) => {
    if (!jobId) { setLogData(null); return; }
    setLogsLoading(true);
    try {
      const data = await apiClient.listWorkLogs({ job_id: jobId, limit: 20 });
      setLogData(data);
    } catch {
      setLogData(null);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs(selectedJobId);
  }, [selectedJobId, loadLogs]);

  // Timer tick
  useEffect(() => {
    if (timerRunning) {
      intervalRef.current = setInterval(() => {
        setElapsed((s) => s + 1);
      }, 1000);
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [timerRunning]);

  const startTimer = () => {
    setTimerStart(new Date());
    setElapsed(0);
    setTimerRunning(true);
  };

  const stopTimer = () => {
    setTimerRunning(false);
  };

  // Compute duration_minutes + started_at/ended_at from mode
  function buildTimeFields(): { duration_minutes?: number; started_at?: string; ended_at?: string } {
    if (timeMode === 'timer' && timerStart && !timerRunning && elapsed > 0) {
      const end = new Date(timerStart.getTime() + elapsed * 1000);
      return {
        started_at: timerStart.toISOString(),
        ended_at: end.toISOString(),
        duration_minutes: Math.max(1, Math.round(elapsed / 60)),
      };
    }
    if (timeMode === 'manual' && manualStart && manualEnd) {
      const s = new Date(manualStart);
      const e = new Date(manualEnd);
      const mins = Math.round((e.getTime() - s.getTime()) / 60000);
      return { started_at: s.toISOString(), ended_at: e.toISOString(), duration_minutes: Math.max(1, mins) };
    }
    if (timeMode === 'quick' && quickHours) {
      const mins = Math.round(parseFloat(quickHours) * 60);
      return { duration_minutes: mins > 0 ? mins : undefined };
    }
    return {};
  }

  const selectedContract = contracts.find((c) => c.id === selectedJobId);

  const handleSubmit = async () => {
    if (!taskDescription.trim()) { setSaveError('Task description is required.'); return; }
    if (!selectedContract) { setSaveError('Select a contract first.'); return; }

    setSaveError(null);
    setSaving(true);

    // Extract contract_id from upwork_job_id ("contract_{id}")
    const upworkContractId = selectedContract.upwork_job_id?.replace(/^contract_/, '') ?? undefined;

    const timeFields = buildTimeFields();

    try {
      await apiClient.createWorkLog({
        job_id: selectedContract.id,
        contract_title: selectedContract.title,
        upwork_contract_id: upworkContractId,
        task_description: taskDescription.trim(),
        notes: notes.trim() || undefined,
        attachment_filename: attachment?.filename,
        attachment_text: attachment?.text || undefined,
        ...timeFields,
      });

      // Reset form
      setTaskDescription('');
      setNotes('');
      setAttachment(null);
      setTimerStart(null);
      setElapsed(0);
      setManualStart('');
      setManualEnd('');
      setQuickHours('');

      // Reload logs
      await loadLogs(selectedJobId);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to save work log.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (logId: string) => {
    try {
      await apiClient.deleteWorkLog(logId);
      setLogData((prev) => prev
        ? { ...prev, logs: prev.logs.filter((l) => l.id !== logId), total: prev.total - 1 }
        : prev
      );
    } catch { /* silent */ }
  };


  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="p-4 space-y-4 flex-shrink-0">

        {/* Contract selector */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Contract</label>
          {contractsLoading ? (
            <p className="text-xs text-gray-400">Loading contracts…</p>
          ) : contracts.length === 0 ? (
            <div className="text-xs text-gray-400 bg-amber-50 rounded-lg p-3">
              No active contracts found. Visit{' '}
              <span className="font-medium">upwork.com/nx/contracts</span> and click{' '}
              <span className="font-medium">📥 Import wins</span> to import your contracts.
            </div>
          ) : (
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-emerald-400"
            >
              <option value="">— Select a contract —</option>
              {contracts.map((c) => (
                <option key={c.id} value={c.id}>{c.title}</option>
              ))}
            </select>
          )}
        </div>

        {/* Time mode toggle */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Time</label>
          <div className="flex gap-1 mb-2">
            {(['timer', 'manual', 'quick'] as TimeMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { setTimeMode(m); setTimerRunning(false); }}
                className={`flex-1 text-xs py-1 rounded-full font-medium transition-colors ${
                  timeMode === m ? 'bg-emerald-100 text-emerald-700' : 'text-gray-400 hover:bg-gray-100'
                }`}
              >
                {m === 'timer' ? '⏱ Timer' : m === 'manual' ? '📅 Manual' : '⌚ Quick'}
              </button>
            ))}
          </div>

          {/* Timer UI */}
          {timeMode === 'timer' && (
            <div className="flex items-center gap-3">
              {!timerRunning && elapsed === 0 ? (
                <button
                  type="button"
                  onClick={startTimer}
                  className="px-4 py-1.5 bg-emerald-600 text-white text-xs rounded-full font-medium hover:bg-emerald-700"
                >
                  ▶ Start
                </button>
              ) : timerRunning ? (
                <>
                  <span className="text-lg font-mono font-bold text-emerald-600 tabular-nums">
                    {formatElapsed(elapsed)}
                  </span>
                  <button
                    type="button"
                    onClick={stopTimer}
                    className="px-4 py-1.5 bg-red-500 text-white text-xs rounded-full font-medium hover:bg-red-600"
                  >
                    ⏹ Stop
                  </button>
                </>
              ) : (
                <>
                  <span className="text-sm font-semibold text-gray-700">
                    {formatElapsed(elapsed)} logged
                  </span>
                  <button
                    type="button"
                    onClick={startTimer}
                    className="text-xs text-gray-400 hover:text-gray-600 underline"
                  >
                    Restart
                  </button>
                </>
              )}
            </div>
          )}

          {/* Manual UI */}
          {timeMode === 'manual' && (
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-[10px] text-gray-400">Start</label>
                <input
                  type="datetime-local"
                  value={manualStart}
                  onChange={(e) => setManualStart(e.target.value)}
                  className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-emerald-400"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] text-gray-400">End</label>
                <input
                  type="datetime-local"
                  value={manualEnd}
                  onChange={(e) => setManualEnd(e.target.value)}
                  className="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-emerald-400"
                />
              </div>
            </div>
          )}

          {/* Quick UI */}
          {timeMode === 'quick' && (
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0.25"
                step="0.25"
                placeholder="1.5"
                value={quickHours}
                onChange={(e) => setQuickHours(e.target.value)}
                className="w-24 text-xs border border-gray-200 rounded px-2 py-1.5 text-center focus:outline-none focus:ring-1 focus:ring-emerald-400"
              />
              <span className="text-xs text-gray-500">hours</span>
              {quickHours && parseFloat(quickHours) > 0 && (
                <span className="text-xs text-emerald-600 font-medium">
                  = {formatMinutes(Math.round(parseFloat(quickHours) * 60))}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Task description */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">What did you do?</label>
          <textarea
            rows={3}
            value={taskDescription}
            onChange={(e) => setTaskDescription(e.target.value)}
            placeholder="Describe the work completed…"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-400 resize-none"
          />
        </div>

        {/* Attachment */}
        <AttachmentPicker value={attachment} onChange={setAttachment} />
        {attachment?.text && !attachment.extracting && (
          <div className="bg-gray-50 rounded p-2">
            <p className="text-[10px] text-gray-500 font-medium mb-1">Extracted content</p>
            <p className="text-[10px] text-gray-600 line-clamp-3">{attachment.text}</p>
          </div>
        )}

        {/* Notes */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Notes <span className="font-normal text-gray-400">(optional)</span>
          </label>
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Additional context, blockers, next steps…"
            className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-400 resize-none"
          />
        </div>

        {/* Error */}
        {saveError && <p className="text-xs text-red-600">{saveError}</p>}

        {/* Submit */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={saving || !taskDescription.trim() || !selectedJobId}
          className="w-full py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : '💾 Log Work'}
        </button>
      </div>

      {/* Work log history */}
      {selectedJobId && (
        <div className="border-t border-gray-100 px-4 pt-3 pb-4 space-y-2 flex-shrink-0">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-600">Recent Entries</p>
            {logData && logData.total_minutes > 0 && (
              <span className="text-xs text-emerald-600 font-medium">
                {formatMinutes(logData.total_minutes)} total
              </span>
            )}
          </div>

          {logsLoading && <p className="text-xs text-gray-400">Loading…</p>}

          {!logsLoading && logData && logData.logs.length === 0 && (
            <p className="text-xs text-gray-400">No entries yet for this contract.</p>
          )}

          {logData?.logs.map((log) => (
            <LogCard key={log.id} log={log} onDelete={handleDelete} />
          ))}

          {logData && logData.total > logData.logs.length && (
            <p className="text-[10px] text-gray-400 text-center">
              Showing {logData.logs.length} of {logData.total} entries
            </p>
          )}
        </div>
      )}
    </div>
  );
}
