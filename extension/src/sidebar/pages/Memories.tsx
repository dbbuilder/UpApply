import { useState, useEffect } from 'react';
import { useAppStore } from '../store';
import { apiClient, Memory, MemoryCreate } from '../../lib/api-client';

export default function MemoriesPage() {
  const { setCurrentView } = useAppStore();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Memory[]>([]);
  const [searching, setSearching] = useState(false);
  const [newMemory, setNewMemory] = useState<MemoryCreate>({
    title: '',
    content: '',
    category: 'project',
    skills_demonstrated: [],
    outcome: '',
  });
  const [newSkill, setNewSkill] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadMemories();
  }, []);

  const loadMemories = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.getMemories();
      setMemories(result);
    } catch (err) {
      console.error('Failed to load memories:', err);
      setError(err instanceof TypeError
        ? 'Server unavailable. Please retry.'
        : 'Failed to load memories.');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }

    setSearching(true);
    try {
      const results = await apiClient.searchMemories(searchQuery);
      setSearchResults(results.map((r) => r.memory));
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setSearching(false);
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

  const displayMemories = searchQuery && searchResults.length > 0 ? searchResults : memories;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setCurrentView('generator')}
          className="text-gray-600 hover:text-gray-900"
        >
          ← Back
        </button>
        <h1 className="font-bold text-gray-900">Memories</h1>
        <div className="w-12" /> {/* Spacer */}
      </header>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Search */}
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="input flex-1"
            placeholder="Search memories..."
          />
          <button
            type="button"
            onClick={handleSearch}
            disabled={searching}
            className="btn-outline"
          >
            {searching ? '...' : 'Search'}
          </button>
        </div>

        {/* Add button */}
        {!showAddForm && (
          <button
            type="button"
            onClick={() => setShowAddForm(true)}
            className="btn-primary w-full"
          >
            + Add Memory
          </button>
        )}

        {/* Add form */}
        {showAddForm && (
          <div className="card animate-slide-up">
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
                  className="input min-h-[100px]"
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
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-8">
            <div className="animate-pulse-slow text-gray-500">Loading memories...</div>
          </div>
        )}

        {error && !loading && (
          <div className="card bg-red-50 text-center py-4">
            <p className="text-sm text-red-700">{error}</p>
            <button type="button" onClick={loadMemories} className="btn-outline text-sm mt-2">
              Retry
            </button>
          </div>
        )}

        {/* Memories list */}
        {!loading && displayMemories.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            <p>{searchQuery ? 'No matching memories found.' : 'No memories yet.'}</p>
          </div>
        )}

        <div className="space-y-3">
          {displayMemories.map((memory) => (
            <div key={memory.id} className="card">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium text-gray-900">{memory.title}</h4>
                    {memory.category && (
                      <span className="badge badge-gray text-xs">{memory.category}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-1 line-clamp-3">{memory.content}</p>
                  {memory.skills_demonstrated && memory.skills_demonstrated.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {memory.skills_demonstrated.map((skill) => (
                        <span key={skill} className="badge badge-green text-xs">
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
          ))}
        </div>
      </div>
    </div>
  );
}
