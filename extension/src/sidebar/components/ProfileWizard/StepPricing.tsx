import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { apiClient } from '../../../lib/api-client';

const TONE_OPTIONS = [
  { value: 'professional', label: 'Professional', desc: 'Formal and business-focused' },
  { value: 'casual', label: 'Casual', desc: 'Friendly and conversational' },
  { value: 'technical', label: 'Technical', desc: 'Detail-oriented and precise' },
];

export default function StepPricing() {
  const { profile, setProfile } = useAppStore();
  const [hourlyMin, setHourlyMin] = useState(profile?.hourly_rate_min?.toString() || '');
  const [hourlyMax, setHourlyMax] = useState(profile?.hourly_rate_max?.toString() || '');
  const [hourlyPreferred, setHourlyPreferred] = useState(
    profile?.hourly_rate_preferred?.toString() || ''
  );
  const [fixedPriceMin, setFixedPriceMin] = useState(
    profile?.fixed_price_minimum?.toString() || ''
  );
  const [hoursPerWeek, setHoursPerWeek] = useState(
    profile?.hours_per_week_available?.toString() || ''
  );
  const [acceptingWork, setAcceptingWork] = useState(
    profile?.currently_accepting_work !== false
  );
  const [tone, setTone] = useState(profile?.tone_preference || 'professional');
  const [uniqueStrengths, setUniqueStrengths] = useState<string[]>(
    profile?.unique_strengths || []
  );
  const [newStrength, setNewStrength] = useState('');

  useEffect(() => {
    if (profile) {
      setHourlyMin(profile.hourly_rate_min?.toString() || '');
      setHourlyMax(profile.hourly_rate_max?.toString() || '');
      setHourlyPreferred(profile.hourly_rate_preferred?.toString() || '');
      setFixedPriceMin(profile.fixed_price_minimum?.toString() || '');
      setHoursPerWeek(profile.hours_per_week_available?.toString() || '');
      setAcceptingWork(profile.currently_accepting_work !== false);
      setTone(profile.tone_preference || 'professional');
      setUniqueStrengths(profile.unique_strengths || []);
    }
  }, [profile]);

  const handleSave = async () => {
    try {
      const updated = await apiClient.updatePricing({
        hourly_rate_min: hourlyMin ? parseFloat(hourlyMin) : undefined,
        hourly_rate_max: hourlyMax ? parseFloat(hourlyMax) : undefined,
        hourly_rate_preferred: hourlyPreferred ? parseFloat(hourlyPreferred) : undefined,
        fixed_price_minimum: fixedPriceMin ? parseFloat(fixedPriceMin) : undefined,
        hours_per_week_available: hoursPerWeek ? parseInt(hoursPerWeek) : undefined,
        currently_accepting_work: acceptingWork,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const handleSaveTone = async () => {
    try {
      const updated = await apiClient.updateProfile({
        tone_preference: tone,
        unique_strengths: uniqueStrengths,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const addStrength = () => {
    if (newStrength.trim() && !uniqueStrengths.includes(newStrength.trim())) {
      const updated = [...uniqueStrengths, newStrength.trim()];
      setUniqueStrengths(updated);
      setNewStrength('');
    }
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Pricing & Availability</h3>
        <p className="text-sm text-gray-600 mt-1">
          Set your rates and communication style
        </p>
      </div>

      {/* Hourly Rate */}
      <div>
        <label className="label">Hourly Rate Range</label>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <p className="text-xs text-gray-500 mb-1">Min</p>
            <div className="relative">
              <span className="absolute left-2 top-2 text-gray-500 text-sm">$</span>
              <input
                type="number"
                value={hourlyMin}
                onChange={(e) => setHourlyMin(e.target.value)}
                onBlur={handleSave}
                className="input pl-5 text-sm"
                placeholder="40"
              />
            </div>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Preferred</p>
            <div className="relative">
              <span className="absolute left-2 top-2 text-gray-500 text-sm">$</span>
              <input
                type="number"
                value={hourlyPreferred}
                onChange={(e) => setHourlyPreferred(e.target.value)}
                onBlur={handleSave}
                className="input pl-5 text-sm"
                placeholder="75"
              />
            </div>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Max</p>
            <div className="relative">
              <span className="absolute left-2 top-2 text-gray-500 text-sm">$</span>
              <input
                type="number"
                value={hourlyMax}
                onChange={(e) => setHourlyMax(e.target.value)}
                onBlur={handleSave}
                className="input pl-5 text-sm"
                placeholder="150"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Fixed Price Minimum */}
      <div>
        <label htmlFor="fixedMin" className="label">
          Minimum Fixed Price Project
        </label>
        <div className="relative">
          <span className="absolute left-3 top-2.5 text-gray-500">$</span>
          <input
            id="fixedMin"
            type="number"
            value={fixedPriceMin}
            onChange={(e) => setFixedPriceMin(e.target.value)}
            onBlur={handleSave}
            className="input pl-7"
            placeholder="500"
          />
        </div>
      </div>

      {/* Availability */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="hours" className="label">
            Hours/Week Available
          </label>
          <input
            id="hours"
            type="number"
            value={hoursPerWeek}
            onChange={(e) => setHoursPerWeek(e.target.value)}
            onBlur={handleSave}
            className="input"
            placeholder="30"
          />
        </div>
        <div>
          <label className="label">Accepting Work?</label>
          <button
            type="button"
            onClick={() => {
              setAcceptingWork(!acceptingWork);
              setTimeout(handleSave, 100);
            }}
            className={`w-full py-2 px-4 rounded-lg font-medium transition-colors ${
              acceptingWork
                ? 'bg-green-100 text-green-700'
                : 'bg-gray-100 text-gray-700'
            }`}
          >
            {acceptingWork ? 'Yes' : 'No'}
          </button>
        </div>
      </div>

      {/* Tone Preference */}
      <div>
        <label className="label">Cover Letter Tone</label>
        <div className="space-y-2">
          {TONE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                setTone(option.value);
                setTimeout(handleSaveTone, 100);
              }}
              className={`w-full text-left p-3 rounded-lg border transition-colors ${
                tone === option.value
                  ? 'border-upwork-green bg-green-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="font-medium text-gray-900">{option.label}</div>
              <div className="text-sm text-gray-500">{option.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Unique Strengths */}
      <div>
        <label className="label">What Makes You Different?</label>
        <p className="text-xs text-gray-500 mb-2">
          These will be emphasized in your cover letters
        </p>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newStrength}
            onChange={(e) => setNewStrength(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addStrength()}
            className="input flex-1"
            placeholder="e.g., 99% on-time delivery rate..."
          />
          <button type="button" onClick={addStrength} className="btn-outline px-3">
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {uniqueStrengths.map((strength) => (
            <span key={strength} className="badge badge-green flex items-center gap-1">
              {strength}
              <button
                type="button"
                onClick={() => {
                  setUniqueStrengths(uniqueStrengths.filter((s) => s !== strength));
                  setTimeout(handleSaveTone, 100);
                }}
                className="ml-1 hover:text-green-900"
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
