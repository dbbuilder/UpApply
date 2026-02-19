import { useState } from 'react';
import { useAppStore } from '../store';

const LEVELS = ['beginner', 'intermediate', 'expert'] as const;

export default function SkillsPage() {
  const { profile, setCurrentView, addSkillToProfile, removeSkillFromProfile, updateSkillInProfile } = useAppStore();
  const [newSkill, setNewSkill] = useState('');
  const [newLevel, setNewLevel] = useState<string>('intermediate');
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);

  const skills = profile?.skills || [];

  const handleAdd = async () => {
    const name = newSkill.trim();
    if (!name) return;
    setAdding(true);
    const success = await addSkillToProfile(name, newLevel);
    setAdding(false);
    if (success) {
      setNewSkill('');
      setNewLevel('intermediate');
    }
  };

  const handleRemove = async (skillName: string) => {
    setRemoving(skillName);
    await removeSkillFromProfile(skillName);
    setRemoving(null);
  };

  const handleLevelChange = async (skillName: string, level: string) => {
    const skill = skills.find(s => s.name === skillName);
    await updateSkillInProfile(skillName, level, skill?.years);
    setEditing(null);
  };

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
          <h1 className="font-bold text-gray-900">Skills</h1>
        </div>
        <span className="text-sm text-gray-500">{skills.length} skills</span>
      </header>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Add new skill */}
        <div className="card">
          <h4 className="font-medium text-gray-900 mb-2">Add Skill</h4>
          <div className="flex gap-2">
            <input
              type="text"
              value={newSkill}
              onChange={(e) => setNewSkill(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && newSkill.trim() && handleAdd()}
              placeholder="e.g. React, Python, AWS..."
              className="input text-sm flex-1"
            />
            <select
              value={newLevel}
              onChange={(e) => setNewLevel(e.target.value)}
              className="input text-sm w-28"
            >
              {LEVELS.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleAdd}
              disabled={adding || !newSkill.trim()}
              className="btn-primary text-sm px-3"
            >
              {adding ? '...' : 'Add'}
            </button>
          </div>
        </div>

        {/* Skills list */}
        <div className="card">
          {skills.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No skills added yet. Add skills to improve job matching.
            </p>
          ) : (
            <div className="space-y-2">
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className="flex items-center justify-between py-2 border-b border-gray-100 last:border-0"
                >
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {skill.name}
                    </span>
                    {editing === skill.name ? (
                      <select
                        value={skill.level || 'beginner'}
                        onChange={(e) => handleLevelChange(skill.name, e.target.value)}
                        onBlur={() => setEditing(null)}
                        className="input text-xs py-0.5 w-28"
                        autoFocus
                      >
                        {LEVELS.map(l => (
                          <option key={l} value={l}>{l}</option>
                        ))}
                      </select>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setEditing(skill.name)}
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          skill.level === 'expert'
                            ? 'bg-green-100 text-green-700'
                            : skill.level === 'intermediate'
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {skill.level || 'beginner'}
                      </button>
                    )}
                    {skill.years && (
                      <span className="text-xs text-gray-400">{skill.years}y</span>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemove(skill.name)}
                    disabled={removing === skill.name}
                    className="text-gray-400 hover:text-red-500 text-sm ml-2"
                    title="Remove skill"
                  >
                    {removing === skill.name ? '...' : '\u00D7'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
