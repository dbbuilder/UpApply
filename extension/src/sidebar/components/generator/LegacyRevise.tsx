import { useState } from 'react';

interface LegacyReviseProps {
  busy: boolean;
  improving: boolean;
  improvementNotes: string[] | null;
  onRegenerate: (feedback: string) => void;
  onImprove: () => void;
}

/** Revision controls for letters from the legacy (generation_v2 off) path, which refine cannot revise. */
export default function LegacyRevise({ busy, improving, improvementNotes, onRegenerate, onImprove }: LegacyReviseProps) {
  const [feedback, setFeedback] = useState('');
  const [showNotes, setShowNotes] = useState(true);

  const regenerate = () => {
    const text = feedback.trim();
    if (!text || busy) return;
    onRegenerate(text);
    setFeedback('');
  };

  return (
    <div className="card">
      <div className="flex gap-2">
        <input
          type="text"
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && regenerate()}
          placeholder="What should be different? (e.g., more technical, shorter...)"
          className="input text-sm flex-1"
          disabled={busy}
        />
        <button
          type="button"
          onClick={regenerate}
          disabled={busy || !feedback.trim()}
          className="btn-outline text-sm disabled:opacity-50"
        >
          Regenerate
        </button>
      </div>

      <button
        type="button"
        onClick={onImprove}
        disabled={improving || busy}
        title="Compare against your won proposals and improve this letter"
        className="w-full btn-outline text-xs py-1.5 mt-2 disabled:opacity-50"
      >
        {improving ? '✨ Comparing…' : '✨ Improve'}
      </button>

      {improvementNotes && improvementNotes.length > 0 && (
        <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 text-xs">
          <button
            type="button"
            onClick={() => setShowNotes(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-amber-800 font-medium"
          >
            <span>{improvementNotes.length} improvement{improvementNotes.length !== 1 ? 's' : ''} applied</span>
            <span>{showNotes ? '▲' : '▼'}</span>
          </button>
          {showNotes && (
            <ul className="px-3 pb-2 space-y-1 text-amber-700">
              {improvementNotes.map((note, i) => (
                <li key={i} className="leading-snug">• {note}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
