import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { apiClient } from '../../../lib/api-client';

export default function StepDealbreakers() {
  const { profile, setProfile } = useAppStore();
  const [avoidKeywords, setAvoidKeywords] = useState<string[]>(
    profile?.avoid_keywords || []
  );
  const [avoidIndustries, setAvoidIndustries] = useState<string[]>(
    profile?.avoid_industries || []
  );
  const [minimumBudget, setMinimumBudget] = useState(
    profile?.minimum_budget?.toString() || ''
  );
  const [minimumHourlyRate, setMinimumHourlyRate] = useState(
    profile?.minimum_hourly_rate?.toString() || ''
  );
  const [redFlags, setRedFlags] = useState<string[]>(
    profile?.red_flag_patterns || []
  );
  const [newKeyword, setNewKeyword] = useState('');
  const [newIndustry, setNewIndustry] = useState('');
  const [newRedFlag, setNewRedFlag] = useState('');

  useEffect(() => {
    if (profile) {
      setAvoidKeywords(profile.avoid_keywords || []);
      setAvoidIndustries(profile.avoid_industries || []);
      setMinimumBudget(profile.minimum_budget?.toString() || '');
      setMinimumHourlyRate(profile.minimum_hourly_rate?.toString() || '');
      setRedFlags(profile.red_flag_patterns || []);
    }
  }, [profile]);

  const handleSave = async () => {
    try {
      const updated = await apiClient.updateDealbreakers({
        avoid_keywords: avoidKeywords,
        avoid_industries: avoidIndustries,
        minimum_budget: minimumBudget ? parseFloat(minimumBudget) : undefined,
        minimum_hourly_rate: minimumHourlyRate ? parseFloat(minimumHourlyRate) : undefined,
        red_flag_patterns: redFlags,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const addKeyword = () => {
    if (newKeyword.trim() && !avoidKeywords.includes(newKeyword.trim())) {
      setAvoidKeywords([...avoidKeywords, newKeyword.trim()]);
      setNewKeyword('');
    }
  };

  const addIndustry = () => {
    if (newIndustry.trim() && !avoidIndustries.includes(newIndustry.trim())) {
      setAvoidIndustries([...avoidIndustries, newIndustry.trim()]);
      setNewIndustry('');
    }
  };

  const addRedFlag = () => {
    if (newRedFlag.trim() && !redFlags.includes(newRedFlag.trim())) {
      setRedFlags([...redFlags, newRedFlag.trim()]);
      setNewRedFlag('');
    }
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Deal Breakers</h3>
        <p className="text-sm text-gray-600 mt-1">
          What should we warn you about or avoid?
        </p>
      </div>

      <div>
        <label className="label">Keywords to Avoid</label>
        <p className="text-xs text-gray-500 mb-2">
          We'll warn you if a job description contains these
        </p>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newKeyword}
            onChange={(e) => setNewKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addKeyword()}
            className="input flex-1"
            placeholder="e.g., cold calling, MLM, crypto..."
          />
          <button type="button" onClick={addKeyword} className="btn-outline px-3">
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {avoidKeywords.map((keyword) => (
            <span key={keyword} className="badge badge-red flex items-center gap-1 pr-1">
              {keyword}
              <button
                type="button"
                onClick={() => {
                  setAvoidKeywords(avoidKeywords.filter((k) => k !== keyword));
                  setTimeout(handleSave, 100);
                }}
                className="ml-1 w-4 h-4 flex items-center justify-center rounded-full hover:bg-red-200 text-red-700 hover:text-red-900 font-bold"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Industries to Avoid</label>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newIndustry}
            onChange={(e) => setNewIndustry(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addIndustry()}
            className="input flex-1"
            placeholder="e.g., gambling, adult content..."
          />
          <button type="button" onClick={addIndustry} className="btn-outline px-3">
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {avoidIndustries.map((industry) => (
            <span key={industry} className="badge badge-red flex items-center gap-1 pr-1">
              {industry}
              <button
                type="button"
                onClick={() => {
                  setAvoidIndustries(avoidIndustries.filter((i) => i !== industry));
                  setTimeout(handleSave, 100);
                }}
                className="ml-1 w-4 h-4 flex items-center justify-center rounded-full hover:bg-red-200 text-red-700 hover:text-red-900 font-bold"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="minBudget" className="label">
            Minimum Fixed Budget
          </label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-gray-500">$</span>
            <input
              id="minBudget"
              type="number"
              value={minimumBudget}
              onChange={(e) => setMinimumBudget(e.target.value)}
              onBlur={handleSave}
              className="input pl-7"
              placeholder="500"
            />
          </div>
        </div>

        <div>
          <label htmlFor="minHourly" className="label">
            Minimum Hourly Rate
          </label>
          <div className="relative">
            <span className="absolute left-3 top-2.5 text-gray-500">$</span>
            <input
              id="minHourly"
              type="number"
              value={minimumHourlyRate}
              onChange={(e) => setMinimumHourlyRate(e.target.value)}
              onBlur={handleSave}
              className="input pl-7"
              placeholder="50"
            />
            <span className="absolute right-3 top-2.5 text-gray-500">/hr</span>
          </div>
        </div>
      </div>

      <div>
        <label className="label">Red Flag Patterns</label>
        <p className="text-xs text-gray-500 mb-2">
          Client patterns to warn about (e.g., "need ASAP", "test project")
        </p>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newRedFlag}
            onChange={(e) => setNewRedFlag(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addRedFlag()}
            className="input flex-1"
            placeholder="e.g., need by tomorrow, unlimited revisions..."
          />
          <button type="button" onClick={addRedFlag} className="btn-outline px-3">
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {redFlags.map((flag) => (
            <span key={flag} className="badge badge-yellow flex items-center gap-1 pr-1">
              {flag}
              <button
                type="button"
                onClick={() => {
                  setRedFlags(redFlags.filter((f) => f !== flag));
                  setTimeout(handleSave, 100);
                }}
                className="ml-1 w-4 h-4 flex items-center justify-center rounded-full hover:bg-yellow-200 text-yellow-700 hover:text-yellow-900 font-bold"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
