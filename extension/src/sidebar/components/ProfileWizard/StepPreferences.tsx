import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { apiClient } from '../../../lib/api-client';

const PROJECT_TYPES = [
  'Web Application',
  'Mobile App',
  'API/Backend',
  'Data Analysis',
  'Machine Learning',
  'E-commerce',
  'SaaS',
  'WordPress/CMS',
];

const INDUSTRIES = [
  'Fintech',
  'Healthcare',
  'E-commerce',
  'SaaS/B2B',
  'Education',
  'Real Estate',
  'Media/Entertainment',
  'Non-profit',
];

const CLIENT_TYPES = ['Startup', 'Small Business', 'Enterprise', 'Agency', 'Individual'];

const TEAM_SIZES = ['Solo', 'Small Team (2-5)', 'Large Team (5+)'];

const DURATIONS = ['Short-term (<1 month)', 'Medium (1-3 months)', 'Long-term (3+ months)', 'Ongoing'];

export default function StepPreferences() {
  const { profile, setProfile } = useAppStore();
  const [projectTypes, setProjectTypes] = useState<string[]>(
    profile?.preferred_project_types || []
  );
  const [industries, setIndustries] = useState<string[]>(
    profile?.preferred_industries || []
  );
  const [clientTypes, setClientTypes] = useState<string[]>(
    profile?.preferred_client_types || []
  );
  const [teamSize, setTeamSize] = useState(profile?.preferred_team_size || '');
  const [duration, setDuration] = useState(profile?.project_duration_preference || '');

  useEffect(() => {
    if (profile) {
      setProjectTypes(profile.preferred_project_types || []);
      setIndustries(profile.preferred_industries || []);
      setClientTypes(profile.preferred_client_types || []);
      setTeamSize(profile.preferred_team_size || '');
      setDuration(profile.project_duration_preference || '');
    }
  }, [profile]);

  const handleSave = async () => {
    try {
      const updated = await apiClient.updatePreferences({
        preferred_project_types: projectTypes,
        preferred_industries: industries,
        preferred_client_types: clientTypes,
        preferred_team_size: teamSize,
        project_duration_preference: duration,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const toggleItem = (
    item: string,
    list: string[],
    setList: (list: string[]) => void
  ) => {
    if (list.includes(item)) {
      setList(list.filter((i) => i !== item));
    } else {
      setList([...list, item]);
    }
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Project Preferences</h3>
        <p className="text-sm text-gray-600 mt-1">
          What kind of projects are you looking for?
        </p>
      </div>

      <div>
        <label className="label">Project Types</label>
        <div className="flex flex-wrap gap-2">
          {PROJECT_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => {
                toggleItem(type, projectTypes, setProjectTypes);
                setTimeout(handleSave, 100);
              }}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                projectTypes.includes(type)
                  ? 'bg-upwork-green text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Preferred Industries</label>
        <div className="flex flex-wrap gap-2">
          {INDUSTRIES.map((industry) => (
            <button
              key={industry}
              type="button"
              onClick={() => {
                toggleItem(industry, industries, setIndustries);
                setTimeout(handleSave, 100);
              }}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                industries.includes(industry)
                  ? 'bg-upwork-green text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {industry}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Client Types</label>
        <div className="flex flex-wrap gap-2">
          {CLIENT_TYPES.map((client) => (
            <button
              key={client}
              type="button"
              onClick={() => {
                toggleItem(client, clientTypes, setClientTypes);
                setTimeout(handleSave, 100);
              }}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                clientTypes.includes(client)
                  ? 'bg-upwork-green text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {client}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Preferred Team Size</label>
        <div className="flex flex-wrap gap-2">
          {TEAM_SIZES.map((size) => (
            <button
              key={size}
              type="button"
              onClick={() => {
                setTeamSize(size);
                setTimeout(handleSave, 100);
              }}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                teamSize === size
                  ? 'bg-upwork-green text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {size}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Project Duration</label>
        <div className="flex flex-wrap gap-2">
          {DURATIONS.map((dur) => (
            <button
              key={dur}
              type="button"
              onClick={() => {
                setDuration(dur);
                setTimeout(handleSave, 100);
              }}
              className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
                duration === dur
                  ? 'bg-upwork-green text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {dur}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
