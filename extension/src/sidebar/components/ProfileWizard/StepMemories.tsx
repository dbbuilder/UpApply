import { useState, useEffect } from 'react';
import { apiClient, Memory, MemoryCreate } from '../../../lib/api-client';

export default function StepMemories() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [extractedMemories, setExtractedMemories] = useState<MemoryCreate[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMemory, setNewMemory] = useState<MemoryCreate>({
    title: '',
    content: '',
    category: 'project',
    skills_demonstrated: [],
    outcome: '',
  });
  const [newSkill, setNewSkill] = useState('');

  useEffect(() => {
    loadMemories();
    loadExtractedMemories();
  }, []);

  const loadMemories = async () => {
    try {
      const result = await apiClient.getMemories();
      setMemories(result);
    } catch (error) {
      console.error('Failed to load memories:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadExtractedMemories = async () => {
    const result = await chrome.storage.local.get('extractedMemories');
    if (result.extractedMemories) {
      setExtractedMemories(result.extractedMemories);
    }
  };

  const importExtractedMemories = async () => {
    if (extractedMemories.length === 0) return;

    setImporting(true);
    try {
      const imported = await apiClient.bulkImportMemories(extractedMemories);
      setMemories([...memories, ...imported]);
      setExtractedMemories([]);
      await chrome.storage.local.remove('extractedMemories');
    } catch (error) {
      console.error('Import failed:', error);
    } finally {
      setImporting(false);
    }
  };

  const addMemory = async () => {
    if (!newMemory.title || !newMemory.content) return;

    try {
      const created = await apiClient.createMemory(newMemory);
      setMemories([created, ...memories]);
      setNewMemory({
        title: '',
        content: '',
        category: 'project',
        skills_demonstrated: [],
        outcome: '',
      });
      setShowAddForm(false);
    } catch (error) {
      console.error('Failed to add memory:', error);
    }
  };

  const deleteMemory = async (id: string) => {
    try {
      await apiClient.deleteMemory(id);
      setMemories(memories.filter((m) => m.id !== id));
    } catch (error) {
      console.error('Failed to delete memory:', error);
    }
  };

  const addSkillToNewMemory = () => {
    if (newSkill.trim() && !newMemory.skills_demonstrated?.includes(newSkill.trim())) {
      setNewMemory({
        ...newMemory,
        skills_demonstrated: [...(newMemory.skills_demonstrated || []), newSkill.trim()],
      });
      setNewSkill('');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-pulse-slow text-gray-500">Loading memories...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Your Experience Memories</h3>
        <p className="text-sm text-gray-600 mt-1">
          Add key projects and achievements to personalize cover letters
        </p>
      </div>

      {/* Extracted memories from resume */}
      {extractedMemories.length > 0 && (
        <div className="card bg-green-50 border-green-200">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium text-green-800">
              {extractedMemories.length} memories extracted from resume
            </h4>
            <button
              type="button"
              onClick={importExtractedMemories}
              disabled={importing}
              className="btn-primary text-sm py-1"
            >
              {importing ? 'Importing...' : 'Import All'}
            </button>
          </div>
          <div className="space-y-2">
            {extractedMemories.slice(0, 3).map((mem, i) => (
              <div key={i} className="text-sm text-green-700">
                • {mem.title}
              </div>
            ))}
            {extractedMemories.length > 3 && (
              <div className="text-sm text-green-600">
                +{extractedMemories.length - 3} more
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add new memory form */}
      {showAddForm ? (
        <div className="card">
          <h4 className="font-medium text-gray-900 mb-4">Add New Memory</h4>
          <div className="space-y-4">
            <div>
              <label className="label">Title</label>
              <input
                type="text"
                value={newMemory.title}
                onChange={(e) => setNewMemory({ ...newMemory, title: e.target.value })}
                className="input"
                placeholder="e.g., Built e-commerce platform for startup"
              />
            </div>

            <div>
              <label className="label">Description</label>
              <textarea
                value={newMemory.content}
                onChange={(e) => setNewMemory({ ...newMemory, content: e.target.value })}
                className="input min-h-[80px]"
                placeholder="Describe the project, your role, and what you accomplished..."
              />
            </div>

            <div>
              <label className="label">Category</label>
              <select
                value={newMemory.category}
                onChange={(e) => setNewMemory({ ...newMemory, category: e.target.value })}
                className="input"
              >
                <option value="project">Project</option>
                <option value="achievement">Achievement</option>
                <option value="skill_demo">Skill Demo</option>
                <option value="feedback">Client Feedback</option>
              </select>
            </div>

            <div>
              <label className="label">Skills Demonstrated</label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newSkill}
                  onChange={(e) => setNewSkill(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addSkillToNewMemory()}
                  className="input flex-1"
                  placeholder="Add skill..."
                />
                <button type="button" onClick={addSkillToNewMemory} className="btn-outline px-3">
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-1">
                {newMemory.skills_demonstrated?.map((skill) => (
                  <span key={skill} className="badge badge-gray">
                    {skill}
                    <button
                      type="button"
                      onClick={() =>
                        setNewMemory({
                          ...newMemory,
                          skills_demonstrated: newMemory.skills_demonstrated?.filter(
                            (s) => s !== skill
                          ),
                        })
                      }
                      className="ml-1"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div>
              <label className="label">Outcome/Result</label>
              <input
                type="text"
                value={newMemory.outcome}
                onChange={(e) => setNewMemory({ ...newMemory, outcome: e.target.value })}
                className="input"
                placeholder="e.g., Increased sales by 40%, launched in 6 weeks..."
              />
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="btn-secondary flex-1"
              >
                Cancel
              </button>
              <button type="button" onClick={addMemory} className="btn-primary flex-1">
                Save Memory
              </button>
            </div>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setShowAddForm(true)}
          className="btn-outline w-full"
        >
          + Add Memory
        </button>
      )}

      {/* Existing memories */}
      <div className="space-y-3">
        {memories.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <p>No memories yet.</p>
            <p className="text-sm mt-1">Add some to personalize your cover letters!</p>
          </div>
        ) : (
          memories.map((memory) => (
            <div key={memory.id} className="card">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <h4 className="font-medium text-gray-900">{memory.title}</h4>
                  <p className="text-sm text-gray-600 mt-1 line-clamp-2">{memory.content}</p>
                  {memory.skills_demonstrated && memory.skills_demonstrated.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {memory.skills_demonstrated.map((skill) => (
                        <span key={skill} className="badge badge-gray text-xs">
                          {skill}
                        </span>
                      ))}
                    </div>
                  )}
                  {memory.outcome && (
                    <p className="text-sm text-green-600 mt-2">Outcome: {memory.outcome}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => deleteMemory(memory.id)}
                  className="text-gray-400 hover:text-red-500 ml-2"
                >
                  ×
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
