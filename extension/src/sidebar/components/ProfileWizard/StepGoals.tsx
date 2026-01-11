import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { apiClient } from '../../../lib/api-client';

export default function StepGoals() {
  const { profile, setProfile } = useAppStore();
  const [careerGoals, setCareerGoals] = useState(profile?.career_goals || '');
  const [idealProject, setIdealProject] = useState(profile?.ideal_project_description || '');
  const [skillsToHighlight, setSkillsToHighlight] = useState<string[]>(
    profile?.skills_to_highlight || []
  );
  const [skillsToDevelop, setSkillsToDevelop] = useState<string[]>(
    profile?.skills_to_develop || []
  );
  const [newHighlightSkill, setNewHighlightSkill] = useState('');
  const [newDevelopSkill, setNewDevelopSkill] = useState('');

  useEffect(() => {
    if (profile) {
      setCareerGoals(profile.career_goals || '');
      setIdealProject(profile.ideal_project_description || '');
      setSkillsToHighlight(profile.skills_to_highlight || []);
      setSkillsToDevelop(profile.skills_to_develop || []);
    }
  }, [profile]);

  const handleSave = async () => {
    try {
      const updated = await apiClient.updateGoals({
        career_goals: careerGoals,
        ideal_project_description: idealProject,
        skills_to_highlight: skillsToHighlight,
        skills_to_develop: skillsToDevelop,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  const addHighlightSkill = () => {
    if (newHighlightSkill.trim() && !skillsToHighlight.includes(newHighlightSkill.trim())) {
      const updated = [...skillsToHighlight, newHighlightSkill.trim()];
      setSkillsToHighlight(updated);
      setNewHighlightSkill('');
    }
  };

  const removeHighlightSkill = (skill: string) => {
    setSkillsToHighlight(skillsToHighlight.filter((s) => s !== skill));
  };

  const addDevelopSkill = () => {
    if (newDevelopSkill.trim() && !skillsToDevelop.includes(newDevelopSkill.trim())) {
      const updated = [...skillsToDevelop, newDevelopSkill.trim()];
      setSkillsToDevelop(updated);
      setNewDevelopSkill('');
    }
  };

  const removeDevelopSkill = (skill: string) => {
    setSkillsToDevelop(skillsToDevelop.filter((s) => s !== skill));
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Your Goals & Aspirations</h3>
        <p className="text-sm text-gray-600 mt-1">
          Help us understand what you're working toward
        </p>
      </div>

      <div>
        <label htmlFor="careerGoals" className="label">
          What are you working toward?
        </label>
        <textarea
          id="careerGoals"
          value={careerGoals}
          onChange={(e) => setCareerGoals(e.target.value)}
          onBlur={handleSave}
          className="input min-h-[80px]"
          placeholder="e.g., Building a reputation as a React specialist, transitioning to full-time freelance..."
        />
      </div>

      <div>
        <label htmlFor="idealProject" className="label">
          Describe your ideal project
        </label>
        <textarea
          id="idealProject"
          value={idealProject}
          onChange={(e) => setIdealProject(e.target.value)}
          onBlur={handleSave}
          className="input min-h-[80px]"
          placeholder="e.g., A challenging web app for a funded startup, with a clear scope and good communication..."
        />
      </div>

      <div>
        <label className="label">Skills you want to USE more</label>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newHighlightSkill}
            onChange={(e) => setNewHighlightSkill(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addHighlightSkill()}
            className="input flex-1"
            placeholder="Add a skill..."
          />
          <button
            type="button"
            onClick={addHighlightSkill}
            className="btn-outline px-3"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {skillsToHighlight.map((skill) => (
            <span
              key={skill}
              className="badge badge-green flex items-center gap-1"
            >
              {skill}
              <button
                type="button"
                onClick={() => removeHighlightSkill(skill)}
                className="ml-1 hover:text-green-900"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>

      <div>
        <label className="label">Skills you want to LEARN/develop</label>
        <div className="flex gap-2 mb-2">
          <input
            type="text"
            value={newDevelopSkill}
            onChange={(e) => setNewDevelopSkill(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addDevelopSkill()}
            className="input flex-1"
            placeholder="Add a skill..."
          />
          <button
            type="button"
            onClick={addDevelopSkill}
            className="btn-outline px-3"
          >
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {skillsToDevelop.map((skill) => (
            <span
              key={skill}
              className="badge badge-yellow flex items-center gap-1"
            >
              {skill}
              <button
                type="button"
                onClick={() => removeDevelopSkill(skill)}
                className="ml-1 hover:text-yellow-900"
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
