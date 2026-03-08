import { useState } from 'react';
import HistoryPage from './History';
import AnalyticsPage from './Analytics';

type TrackTab = 'history' | 'analytics';

export default function TrackPage() {
  const [activeTab, setActiveTab] = useState<TrackTab>('history');

  return (
    <div className="flex flex-col h-full">
      <div className="bg-white border-b px-4 pt-3 flex-shrink-0">
        <h1 className="font-bold text-gray-900 text-sm mb-2">Track</h1>
        <div className="flex gap-1 pb-2">
          {([
            { id: 'history' as const, label: 'Pipeline' },
            { id: 'analytics' as const, label: 'Trends' },
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
      <div className="flex-1 overflow-auto [&>div>header]:hidden">
        {activeTab === 'history' && <HistoryPage />}
        {activeTab === 'analytics' && <AnalyticsPage />}
      </div>
    </div>
  );
}
