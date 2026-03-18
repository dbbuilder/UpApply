import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../store';
import { apiClient } from '../../lib/api-client';

type Section = 'identity' | 'goals' | 'preferences' | 'dealbreakers' | 'pricing';

const TONE_OPTIONS = ['professional', 'casual', 'technical'];
const PROJECT_TYPES = ['Web Development', 'Mobile App', 'API/Backend', 'Data Science', 'DevOps', 'UI/UX Design', 'Consulting', 'AI/ML'];
const INDUSTRIES = ['Technology', 'Healthcare', 'Finance', 'Education', 'E-commerce', 'SaaS', 'Media', 'Non-profit'];
const CLIENT_TYPES = ['Startup', 'Small Business', 'Enterprise', 'Agency', 'Individual'];
const TEAM_SIZES = ['Solo', 'Small (2-5)', 'Medium (6-15)', 'Large (15+)'];
const DURATIONS = ['Less than 1 month', '1-3 months', '3-6 months', '6+ months'];

function TagInput({ values, onChange, placeholder }: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState('');

  const handleAdd = () => {
    const val = input.trim();
    if (val && !values.includes(val)) {
      onChange([...values, val]);
      setInput('');
    }
  };

  return (
    <div>
      <div className="flex gap-1 flex-wrap mb-1">
        {values.map(v => (
          <span key={v} className="badge badge-gray inline-flex items-center gap-1 text-xs">
            {v}
            <button type="button" onClick={() => onChange(values.filter(x => x !== v))} className="text-gray-400 hover:text-red-500">&times;</button>
          </span>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleAdd())}
          placeholder={placeholder}
          className="input text-sm flex-1"
        />
        <button type="button" onClick={handleAdd} disabled={!input.trim()} className="btn-outline text-xs px-2">+</button>
      </div>
    </div>
  );
}

function CheckboxGroup({ options, values, onChange }: {
  options: string[];
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (opt: string) => {
    onChange(values.includes(opt) ? values.filter(v => v !== opt) : [...values, opt]);
  };

  return (
    <div className="flex flex-wrap gap-1">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          onClick={() => toggle(opt)}
          className={`text-xs px-2 py-1 rounded-full border transition-colors ${
            values.includes(opt)
              ? 'bg-emerald-100 border-emerald-300 text-emerald-700'
              : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

export default function EditProfilePage() {
  const { profile, setCurrentView, loadProfile } = useAppStore();
  const [section, setSection] = useState<Section>('identity');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Identity fields
  const [fullName, setFullName] = useState('');
  const [professionalTitle, setProfessionalTitle] = useState('');
  const [bio, setBio] = useState('');
  const [preferredClosing, setPreferredClosing] = useState('');

  // Goals fields
  const [careerGoals, setCareerGoals] = useState('');
  const [idealProject, setIdealProject] = useState('');
  const [skillsHighlight, setSkillsHighlight] = useState<string[]>([]);
  const [skillsDevelop, setSkillsDevelop] = useState<string[]>([]);

  // Preferences fields
  const [projectTypes, setProjectTypes] = useState<string[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [clientTypes, setClientTypes] = useState<string[]>([]);
  const [clientLocations, setClientLocations] = useState<string[]>([]);
  const [teamSize, setTeamSize] = useState('');
  const [duration, setDuration] = useState('');

  // Dealbreakers fields
  const [avoidKeywords, setAvoidKeywords] = useState<string[]>([]);
  const [avoidIndustries, setAvoidIndustries] = useState<string[]>([]);
  const [minBudget, setMinBudget] = useState('');
  const [minHourlyRate, setMinHourlyRate] = useState('');
  const [redFlags, setRedFlags] = useState<string[]>([]);

  // Pricing fields
  const [hourlyMin, setHourlyMin] = useState('');
  const [hourlyMax, setHourlyMax] = useState('');
  const [hourlyPreferred, setHourlyPreferred] = useState('');
  const [fixedMin, setFixedMin] = useState('');
  const [hoursPerWeek, setHoursPerWeek] = useState('');
  const [acceptingWork, setAcceptingWork] = useState(true);
  const [tone, setTone] = useState('professional');
  const [strengths, setStrengths] = useState<string[]>([]);

  // Load profile data into form
  useEffect(() => {
    if (!profile) return;
    setFullName(profile.full_name || '');
    setProfessionalTitle(profile.professional_title || '');
    setBio(profile.bio || '');
    setPreferredClosing(profile.preferred_closing || '');
    setCareerGoals(profile.career_goals || '');
    setIdealProject(profile.ideal_project_description || '');
    setSkillsHighlight(profile.skills_to_highlight || []);
    setSkillsDevelop(profile.skills_to_develop || []);
    setProjectTypes(profile.preferred_project_types || []);
    setIndustries(profile.preferred_industries || []);
    setClientTypes(profile.preferred_client_types || []);
    setClientLocations(profile.preferred_client_locations || []);
    setTeamSize(profile.preferred_team_size || '');
    setDuration(profile.project_duration_preference || '');
    setAvoidKeywords(profile.avoid_keywords || []);
    setAvoidIndustries(profile.avoid_industries || []);
    setMinBudget(profile.minimum_budget?.toString() || '');
    setMinHourlyRate(profile.minimum_hourly_rate?.toString() || '');
    setRedFlags(profile.red_flag_patterns || []);
    setHourlyMin(profile.hourly_rate_min?.toString() || '');
    setHourlyMax(profile.hourly_rate_max?.toString() || '');
    setHourlyPreferred(profile.hourly_rate_preferred?.toString() || '');
    setFixedMin(profile.fixed_price_minimum?.toString() || '');
    setHoursPerWeek(profile.hours_per_week_available?.toString() || '');
    setAcceptingWork(profile.currently_accepting_work !== false);
    setTone(profile.tone_preference || 'professional');
    setStrengths(profile.unique_strengths || []);
  }, [profile]);

  const flashSaved = useCallback(() => {
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }, []);

  const saveIdentity = async () => {
    setSaving(true);
    try {
      await apiClient.updateProfile({
        full_name: fullName,
        professional_title: professionalTitle,
        bio,
        preferred_closing: preferredClosing,
      });
      await loadProfile();
      flashSaved();
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const saveGoals = async () => {
    setSaving(true);
    try {
      await apiClient.updateGoals({
        career_goals: careerGoals,
        ideal_project_description: idealProject,
        skills_to_highlight: skillsHighlight,
        skills_to_develop: skillsDevelop,
      });
      await loadProfile();
      flashSaved();
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const savePreferences = async () => {
    setSaving(true);
    try {
      await apiClient.updatePreferences({
        preferred_project_types: projectTypes,
        preferred_industries: industries,
        preferred_client_types: clientTypes,
        preferred_client_locations: clientLocations,
        preferred_team_size: teamSize || undefined,
        project_duration_preference: duration || undefined,
      });
      await loadProfile();
      flashSaved();
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const saveDealbreakers = async () => {
    setSaving(true);
    try {
      await apiClient.updateDealbreakers({
        avoid_keywords: avoidKeywords,
        avoid_industries: avoidIndustries,
        minimum_budget: minBudget ? parseFloat(minBudget) : undefined,
        minimum_hourly_rate: minHourlyRate ? parseFloat(minHourlyRate) : undefined,
        red_flag_patterns: redFlags,
      });
      await loadProfile();
      flashSaved();
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const savePricing = async () => {
    setSaving(true);
    try {
      await apiClient.updatePricing({
        hourly_rate_min: hourlyMin ? parseFloat(hourlyMin) : undefined,
        hourly_rate_max: hourlyMax ? parseFloat(hourlyMax) : undefined,
        hourly_rate_preferred: hourlyPreferred ? parseFloat(hourlyPreferred) : undefined,
        fixed_price_minimum: fixedMin ? parseFloat(fixedMin) : undefined,
        hours_per_week_available: hoursPerWeek ? parseInt(hoursPerWeek) : undefined,
        currently_accepting_work: acceptingWork,
      });
      await apiClient.updateProfile({
        tone_preference: tone,
        unique_strengths: strengths,
      });
      await loadProfile();
      flashSaved();
    } catch (e) {
      console.error('Save failed:', e);
    }
    setSaving(false);
  };

  const handleSave = () => {
    switch (section) {
      case 'identity': return saveIdentity();
      case 'goals': return saveGoals();
      case 'preferences': return savePreferences();
      case 'dealbreakers': return saveDealbreakers();
      case 'pricing': return savePricing();
    }
  };

  const sections: { id: Section; label: string }[] = [
    { id: 'identity', label: 'Identity' },
    { id: 'goals', label: 'Goals' },
    { id: 'preferences', label: 'Preferences' },
    { id: 'dealbreakers', label: 'Dealbreakers' },
    { id: 'pricing', label: 'Pricing' },
  ];

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCurrentView('generator')}
            className="text-gray-400 hover:text-gray-600"
          >
            &larr;
          </button>
          <h1 className="font-bold text-gray-900">Edit Profile</h1>
        </div>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="btn-primary text-sm px-3 py-1"
        >
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
        </button>
      </header>

      {/* Section tabs */}
      <div className="bg-white border-b px-2 py-1 flex gap-1 overflow-x-auto">
        {sections.map(s => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={`text-xs px-2 py-1 rounded whitespace-nowrap ${
              section === s.id
                ? 'bg-emerald-100 text-emerald-700 font-medium'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {section === 'identity' && (
          <>
            <div className="card space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Full Name</label>
                <input type="text" value={fullName} onChange={e => setFullName(e.target.value)} className="input text-sm w-full" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Professional Title</label>
                <input type="text" value={professionalTitle} onChange={e => setProfessionalTitle(e.target.value)} className="input text-sm w-full" placeholder="e.g. Full-Stack Developer" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Bio / Summary</label>
                <textarea value={bio} onChange={e => setBio(e.target.value)} rows={4} className="input text-sm w-full" placeholder="Brief professional summary..." />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Preferred Closing</label>
                <textarea value={preferredClosing} onChange={e => setPreferredClosing(e.target.value)} rows={3} className="input text-sm w-full" placeholder={"e.g.\nBest regards,\nChris"} />
              </div>
            </div>
          </>
        )}

        {section === 'goals' && (
          <>
            <div className="card space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Career Goals</label>
                <textarea value={careerGoals} onChange={e => setCareerGoals(e.target.value)} rows={3} className="input text-sm w-full" placeholder="What are you working toward?" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Ideal Project Description</label>
                <textarea value={idealProject} onChange={e => setIdealProject(e.target.value)} rows={3} className="input text-sm w-full" placeholder="Describe your ideal project..." />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Skills to Highlight</label>
                <TagInput values={skillsHighlight} onChange={setSkillsHighlight} placeholder="Skills you want to USE more" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Skills to Develop</label>
                <TagInput values={skillsDevelop} onChange={setSkillsDevelop} placeholder="Skills you want to LEARN" />
              </div>
            </div>
          </>
        )}

        {section === 'preferences' && (
          <>
            <div className="card space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Project Types</label>
                <CheckboxGroup options={PROJECT_TYPES} values={projectTypes} onChange={setProjectTypes} />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Industries</label>
                <CheckboxGroup options={INDUSTRIES} values={industries} onChange={setIndustries} />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Client Types</label>
                <CheckboxGroup options={CLIENT_TYPES} values={clientTypes} onChange={setClientTypes} />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Preferred Client Locations</label>
                <p className="text-xs text-gray-400 mb-1">Countries/regions that get a score boost (e.g. "United States", "Canada")</p>
                <TagInput values={clientLocations} onChange={setClientLocations} placeholder="Add country or region…" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Team Size</label>
                <div className="flex flex-wrap gap-1">
                  {TEAM_SIZES.map(s => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setTeamSize(teamSize === s ? '' : s)}
                      className={`text-xs px-2 py-1 rounded-full border ${
                        teamSize === s
                          ? 'bg-emerald-100 border-emerald-300 text-emerald-700'
                          : 'bg-white border-gray-200 text-gray-600'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Preferred Duration</label>
                <div className="flex flex-wrap gap-1">
                  {DURATIONS.map(d => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDuration(duration === d ? '' : d)}
                      className={`text-xs px-2 py-1 rounded-full border ${
                        duration === d
                          ? 'bg-emerald-100 border-emerald-300 text-emerald-700'
                          : 'bg-white border-gray-200 text-gray-600'
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {section === 'dealbreakers' && (
          <>
            <div className="card space-y-3">
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Avoid Keywords</label>
                <TagInput values={avoidKeywords} onChange={setAvoidKeywords} placeholder="Words that signal bad jobs" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Avoid Industries</label>
                <TagInput values={avoidIndustries} onChange={setAvoidIndustries} placeholder="Industries to skip" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Red Flag Patterns</label>
                <TagInput values={redFlags} onChange={setRedFlags} placeholder='e.g. "unpaid trial", "equity only"' />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-medium text-gray-600 mb-1 block">Min Budget ($)</label>
                  <input type="number" value={minBudget} onChange={e => setMinBudget(e.target.value)} className="input text-sm w-full" placeholder="0" />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-600 mb-1 block">Min Hourly Rate ($)</label>
                  <input type="number" value={minHourlyRate} onChange={e => setMinHourlyRate(e.target.value)} className="input text-sm w-full" placeholder="0" />
                </div>
              </div>
            </div>
          </>
        )}

        {section === 'pricing' && (
          <>
            <div className="card space-y-3">
              <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide">Hourly Rates</h4>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Min ($)</label>
                  <input type="number" value={hourlyMin} onChange={e => setHourlyMin(e.target.value)} className="input text-sm w-full" />
                </div>
                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Preferred ($)</label>
                  <input type="number" value={hourlyPreferred} onChange={e => setHourlyPreferred(e.target.value)} className="input text-sm w-full" />
                </div>
                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Max ($)</label>
                  <input type="number" value={hourlyMax} onChange={e => setHourlyMax(e.target.value)} className="input text-sm w-full" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Fixed Price Min ($)</label>
                  <input type="number" value={fixedMin} onChange={e => setFixedMin(e.target.value)} className="input text-sm w-full" />
                </div>
                <div>
                  <label className="text-xs text-gray-600 mb-1 block">Hours/Week</label>
                  <input type="number" value={hoursPerWeek} onChange={e => setHoursPerWeek(e.target.value)} className="input text-sm w-full" />
                </div>
              </div>

              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={acceptingWork} onChange={e => setAcceptingWork(e.target.checked)} className="rounded" />
                <span className="text-sm text-gray-700">Currently accepting work</span>
              </label>
            </div>

            <div className="card space-y-3">
              <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide">Tone & Strengths</h4>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Cover Letter Tone</label>
                <div className="flex gap-1">
                  {TONE_OPTIONS.map(t => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTone(t)}
                      className={`text-xs px-2 py-1 rounded-full border capitalize ${
                        tone === t
                          ? 'bg-emerald-100 border-emerald-300 text-emerald-700'
                          : 'bg-white border-gray-200 text-gray-600'
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600 mb-1 block">Unique Strengths</label>
                <TagInput values={strengths} onChange={setStrengths} placeholder="What sets you apart?" />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
