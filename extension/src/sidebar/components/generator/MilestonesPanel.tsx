import type { MilestoneSuggestion } from '../../../lib/api-client';

interface MilestonesPanelProps {
  milestones: MilestoneSuggestion[];
  generatingMilestones: boolean;
  fillingMilestones: boolean;
  milestonesBudget: string;
  budgetPlaceholder: string | null | undefined;
  setMilestonesBudget: (v: string) => void;
  onGenerate: () => void;
  onFill: () => void;
}

export default function MilestonesPanel({
  milestones,
  generatingMilestones,
  fillingMilestones,
  milestonesBudget,
  budgetPlaceholder,
  setMilestonesBudget,
  onGenerate,
  onFill,
}: MilestonesPanelProps) {
  return (
    <div className="card animate-slide-up">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium text-gray-900">Milestones</h4>
        {milestones.length > 0 && (
          <button
            type="button"
            onClick={onFill}
            disabled={fillingMilestones}
            className="btn-primary text-xs py-1 px-3 disabled:opacity-60"
          >
            {fillingMilestones ? 'Filling...' : 'Fill Milestones ↵'}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 mb-3">
        <label className="text-xs font-medium text-gray-600 whitespace-nowrap">Total $</label>
        <input
          type="text"
          value={milestonesBudget}
          onChange={e => setMilestonesBudget(e.target.value.replace(/[^0-9.]/g, ''))}
          className="input text-sm flex-1"
          placeholder={budgetPlaceholder ?? 'e.g. 6500'}
        />
        <button
          type="button"
          onClick={onGenerate}
          disabled={generatingMilestones}
          className="btn-outline text-xs py-1 px-3 disabled:opacity-60 whitespace-nowrap"
        >
          {generatingMilestones ? '…' : milestones.length ? 'Regenerate' : 'Generate'}
        </button>
      </div>

      {milestones.length > 0 && (
        <div className="space-y-3">
          {milestones.map((ms, i) => (
            <div key={i} className="border border-gray-100 rounded-lg p-2 text-sm">
              <div className="font-medium text-gray-800">{ms.description}</div>
              <div className="flex gap-4 mt-1 text-gray-500 text-xs">
                <span>Day {ms.days_from_start}</span>
                <span>${ms.amount.toFixed(0)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {!milestones.length && (
        <p className="text-xs text-gray-400">Set total budget and click Generate.</p>
      )}
    </div>
  );
}
