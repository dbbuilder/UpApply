import { useState } from 'react';
import MemoriesPage from './Memories';
import SkillsPage from './Skills';
import EditProfilePage from './EditProfile';
import OptimizePage from './OptimizePage';
import FactsPage from './FactsPage';
import RulesPage from './RulesPage';

type MeTab = 'profile' | 'skills' | 'memories' | 'facts' | 'rules' | 'optimize';

export default function MePage() {
  const [activeTab, setActiveTab] = useState<MeTab>('profile');

  return (
    <div className="flex flex-col h-full">
      {/* Sub-nav */}
      <div className="bg-white border-b px-4 pt-3 flex-shrink-0">
        <div className="flex gap-1 pb-2">
          {(['profile', 'skills', 'memories', 'facts', 'rules', 'optimize'] as MeTab[]).map(tab => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Content — hide the sub-page's own back-button header */}
      <div className="flex-1 overflow-auto [&>div>header]:hidden">
        {activeTab === 'profile' && <EditProfilePage />}
        {activeTab === 'skills' && <SkillsPage />}
        {activeTab === 'memories' && <MemoriesPage />}
        {activeTab === 'facts' && <FactsPage />}
        {activeTab === 'rules' && <RulesPage />}
        {activeTab === 'optimize' && <OptimizePage />}
      </div>
    </div>
  );
}
