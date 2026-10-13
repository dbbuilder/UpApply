import { useState } from 'react';
import type { RefineMessage } from '../../../lib/api-client';

interface RefineChatProps {
  messages: RefineMessage[];
  warnings: string[];
  sending: boolean;
  error: string | null;
  onSend: (message: string) => void;
}

export default function RefineChat({ messages, warnings, sending, error, onSend }: RefineChatProps) {
  const [text, setText] = useState('');

  const send = () => {
    const message = text.trim();
    if (!message || sending) return;
    onSend(message);
    setText('');
  };

  return (
    <div className="card">
      <h4 className="font-medium text-gray-900 mb-2">Refine</h4>

      {messages.length > 0 && (
        <ul className="space-y-1 mb-2 text-xs max-h-[160px] overflow-auto">
          {messages.map((m, i) => (
            <li key={i} className={m.role === 'user' ? 'text-gray-800' : 'text-emerald-700'}>
              {m.role === 'user' ? `You: ${m.content}` : 'Draft updated'}
            </li>
          ))}
        </ul>
      )}

      {warnings.length > 0 && (
        <ul className="mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 space-y-1">
          {warnings.map((w, i) => (
            <li key={i} className="leading-snug">• {w}</li>
          ))}
        </ul>
      )}

      {error && <p className="text-xs text-red-600 mb-2">{error}</p>}

      <div className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder='e.g. "mention the Azure migration", "it was 160 servers", "shorter"'
          className="input text-sm flex-1"
          maxLength={4000}
          disabled={sending}
        />
        <button
          type="button"
          onClick={send}
          disabled={sending || !text.trim()}
          className="btn-primary text-sm disabled:opacity-50"
        >
          {sending ? 'Revising…' : 'Send'}
        </button>
      </div>
    </div>
  );
}
