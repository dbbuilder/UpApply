import { useState, useEffect, useRef } from 'react';
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

  // ChatGPT memory.json import
  const [showImport, setShowImport] = useState(false);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importPreview, setImportPreview] = useState<{ count: number; samples: string[] } | null>(null);
  const [parsedMemories, setParsedMemories] = useState<MemoryCreate[] | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ChatGPT conversations.json import
  const [showConvImport, setShowConvImport] = useState(false);
  const [convImporting, setConvImporting] = useState(false);
  const [convStatus, setConvStatus] = useState<string | null>(null);
  const convFileRef = useRef<HTMLInputElement>(null);

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

  // ChatGPT import helpers
  const guessCategory = (text: string): string => {
    const t = text.toLowerCase();
    if (/\b(built|developed|created|designed|architected|launched|shipped|deployed)\b/.test(t)) return 'project';
    if (/\b(hired|client responded|won|landed|closed|got the job)\b/.test(t)) return 'achievement';
    if (/\b(feedback|client said|they mentioned|review|rating)\b/.test(t)) return 'feedback';
    if (/\b(learned|lesson|mistake|next time|should have|realized)\b/.test(t)) return 'lesson';
    if (/\b(expert|proficient|years? experience|skilled in|specialist)\b/.test(t)) return 'skill_demo';
    return 'project';
  };

  const makeTitle = (text: string): string => {
    const m = text.trim().match(/^([^.!?]{10,80}[.!?])/);
    if (m) return m[1].trim().slice(0, 80);
    const short = text.trim().slice(0, 60);
    return text.length > 60 ? short.replace(/\s\S+$/, '') + '…' : short;
  };

  const parseMemoryFile = (raw: string): MemoryCreate[] => {
    const data = JSON.parse(raw);
    let items: unknown[] = [];
    if (Array.isArray(data)) {
      items = data;
    } else if (data && typeof data === 'object') {
      for (const key of ['memories', 'memory', 'items', 'data']) {
        if (Array.isArray((data as Record<string, unknown>)[key])) {
          items = (data as Record<string, unknown>)[key] as unknown[];
          break;
        }
      }
    }
    const texts: string[] = [];
    for (const item of items) {
      if (typeof item === 'string' && item.trim()) {
        texts.push(item.trim());
      } else if (item && typeof item === 'object') {
        const obj = item as Record<string, unknown>;
        const text = obj.memory ?? obj.content ?? obj.text ?? obj.value;
        if (typeof text === 'string' && text.trim()) texts.push(text.trim());
      }
    }
    return texts.map((t) => ({ title: makeTitle(t), content: t, category: guessCategory(t) }));
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportStatus(null);
    setImportPreview(null);
    setParsedMemories(null);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const mems = parseMemoryFile(reader.result as string);
        if (mems.length === 0) {
          setImportStatus('No memories found in this file. Make sure it\'s the memory.json from your ChatGPT export.');
          return;
        }
        setParsedMemories(mems);
        setImportPreview({
          count: mems.length,
          samples: mems.slice(0, 3).map((m) => m.content.slice(0, 90) + (m.content.length > 90 ? '…' : '')),
        });
      } catch {
        setImportStatus('Could not parse this file. Make sure you selected memory.json from your ChatGPT export zip.');
      }
    };
    reader.readAsText(file);
  };

  const handleImport = async () => {
    if (!parsedMemories?.length) return;
    setImporting(true);
    setImportStatus('Importing…');
    try {
      const imported = await apiClient.bulkImportMemories(parsedMemories);
      setImportStatus(`Imported ${imported.length} memories successfully.`);
      setParsedMemories(null);
      setImportPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await loadMemories();
    } catch {
      setImportStatus('Import failed. Please try again.');
    } finally {
      setImporting(false);
    }
  };

  const handleConvImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setConvStatus('Uploading and analyzing conversations… this may take a minute.');
    setConvImporting(true);
    try {
      const result = await apiClient.importChatGPTConversations(file);
      setConvStatus(
        `Done! ${result.memories_imported} memories + ${result.proposals_imported} cover letter examples extracted from ${result.conversations_processed} conversations.`
      );
      await loadMemories();
    } catch {
      setConvStatus('Import failed. Check that you selected conversations.json from your ChatGPT export.');
    } finally {
      setConvImporting(false);
      if (convFileRef.current) convFileRef.current.value = '';
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

        {/* ChatGPT Import */}
        <div className="border border-dashed border-gray-200 rounded-lg">
          <button
            type="button"
            onClick={() => { setShowImport((v) => !v); setImportStatus(null); setImportPreview(null); setParsedMemories(null); }}
            className="w-full flex items-center justify-between px-4 py-3 text-sm text-gray-600 hover:text-gray-900"
          >
            <span className="font-medium">↑ Import from ChatGPT</span>
            <span className="text-gray-400 text-xs">{showImport ? '▲' : '▼'}</span>
          </button>

          {showImport && (
            <div className="px-4 pb-4 space-y-3 border-t border-gray-100">
              {/* Instructions */}
              <div className="bg-blue-50 rounded-lg p-3 space-y-2 text-xs text-blue-800">
                <p className="font-semibold">How to export your ChatGPT memories:</p>
                <ol className="space-y-1 list-decimal list-inside">
                  <li>Go to <span className="font-mono bg-blue-100 px-1 rounded">chatgpt.com</span> → Settings</li>
                  <li>Click <strong>Data Controls</strong> → <strong>Export data</strong></li>
                  <li>Confirm the export — you'll get an email with a download link</li>
                  <li>Download the zip and open it</li>
                  <li>Find the file called <span className="font-mono bg-blue-100 px-1 rounded">memory.json</span></li>
                  <li>Upload it below</li>
                </ol>
              </div>

              {/* File picker */}
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Select memory.json
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,application/json"
                  onChange={handleFileSelect}
                  className="block w-full text-xs text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
                />
              </div>

              {/* Preview */}
              {importPreview && (
                <div className="bg-gray-50 rounded p-3 space-y-1">
                  <p className="text-xs font-medium text-gray-700">
                    Found {importPreview.count} memories — preview:
                  </p>
                  {importPreview.samples.map((s, i) => (
                    <p key={i} className="text-xs text-gray-500 truncate">• {s}</p>
                  ))}
                  {importPreview.count > 3 && (
                    <p className="text-xs text-gray-400">…and {importPreview.count - 3} more</p>
                  )}
                </div>
              )}

              {/* Status */}
              {importStatus && (
                <p className={`text-xs ${importStatus.includes('successfully') ? 'text-green-600' : 'text-red-500'}`}>
                  {importStatus}
                </p>
              )}

              {/* Import button */}
              {parsedMemories && (
                <button
                  type="button"
                  onClick={handleImport}
                  disabled={importing}
                  className="btn-primary w-full text-sm disabled:opacity-60"
                >
                  {importing ? 'Importing…' : `Import ${parsedMemories.length} memories`}
                </button>
              )}
            </div>
          )}
        </div>

        {/* conversations.json import — AI-extracted memories + cover letters */}
        <div className="border border-dashed border-emerald-200 rounded-lg">
          <button
            type="button"
            onClick={() => { setShowConvImport((v) => !v); setConvStatus(null); }}
            className="w-full flex items-center justify-between px-4 py-3 text-sm text-gray-600 hover:text-gray-900"
          >
            <span className="font-medium">🤖 Import conversations.json <span className="text-emerald-600 font-semibold">(AI-powered)</span></span>
            <span className="text-gray-400 text-xs">{showConvImport ? '▲' : '▼'}</span>
          </button>

          {showConvImport && (
            <div className="px-4 pb-4 space-y-3 border-t border-emerald-100">
              <div className="bg-emerald-50 rounded-lg p-3 space-y-2 text-xs text-emerald-800">
                <p className="font-semibold">Extracts memories + cover letter examples from your full chat history:</p>
                <ol className="space-y-1 list-decimal list-inside">
                  <li>Export your data from <span className="font-mono bg-emerald-100 px-1 rounded">chatgpt.com</span> → Settings → Data Controls</li>
                  <li>Unzip the download and find <span className="font-mono bg-emerald-100 px-1 rounded">conversations.json</span></li>
                  <li>Upload it below — Claude reads every conversation and pulls out project stories, wins, and cover letters</li>
                </ol>
                <p className="text-emerald-600">This takes 1-3 minutes depending on how many conversations you have.</p>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Select conversations.json
                </label>
                <input
                  ref={convFileRef}
                  type="file"
                  accept=".json,application/json"
                  onChange={handleConvImport}
                  disabled={convImporting}
                  className="block w-full text-xs text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100 cursor-pointer disabled:opacity-50"
                />
              </div>

              {convImporting && (
                <div className="flex items-center gap-2 text-xs text-emerald-700">
                  <div className="w-3 h-3 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
                  Analyzing with Claude…
                </div>
              )}

              {convStatus && (
                <p className={`text-xs ${convStatus.includes('Done') ? 'text-emerald-600 font-medium' : convStatus.includes('failed') ? 'text-red-500' : 'text-gray-500'}`}>
                  {convStatus}
                </p>
              )}
            </div>
          )}
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
