import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { apiClient } from '../../../lib/api-client';

export default function StepIdentity() {
  const { profile, setProfile } = useAppStore();
  const [fullName, setFullName] = useState(profile?.full_name || '');
  const [professionalTitle, setProfessionalTitle] = useState(profile?.professional_title || '');
  const [bio, setBio] = useState(profile?.bio || '');
  const [preferredClosing, setPreferredClosing] = useState(profile?.preferred_closing || '');
  const [resumeText, setResumeText] = useState('');
  const [importing, setImporting] = useState(false);
  const [importSuccess, setImportSuccess] = useState(false);

  useEffect(() => {
    if (profile) {
      setFullName(profile.full_name || '');
      setProfessionalTitle(profile.professional_title || '');
      setBio(profile.bio || '');
      setPreferredClosing(profile.preferred_closing || '');
    }
  }, [profile]);

  const handleImportResume = async () => {
    if (!resumeText.trim()) return;

    setImporting(true);
    try {
      const result = await apiClient.importResume(resumeText);

      // Update local state with imported data
      if (result.full_name) setFullName(result.full_name);
      if (result.professional_title) setProfessionalTitle(result.professional_title);
      if (result.bio) setBio(result.bio);

      // Reload profile
      const updatedProfile = await apiClient.getProfile();
      setProfile(updatedProfile);

      setImportSuccess(true);
      setResumeText('');

      // If there are extracted memories, store them for step 6
      if (result.extracted_memories?.length) {
        await chrome.storage.local.set({
          extractedMemories: result.extracted_memories,
        });
      }
    } catch (error) {
      console.error('Import failed:', error);
    } finally {
      setImporting(false);
    }
  };

  const handleSave = async () => {
    try {
      const updated = await apiClient.updateProfile({
        full_name: fullName,
        professional_title: professionalTitle,
        bio: bio,
        preferred_closing: preferredClosing,
      });
      setProfile(updated);
    } catch (error) {
      console.error('Save failed:', error);
    }
  };

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold text-gray-900">Let's get to know you</h3>
        <p className="text-sm text-gray-600 mt-1">
          Start by importing your resume or fill in manually
        </p>
      </div>

      {/* Resume import */}
      <div className="card">
        <h4 className="font-medium text-gray-900 mb-3">Import from Resume</h4>
        <textarea
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          placeholder="Paste your resume text here..."
          className="input min-h-[120px] text-sm"
        />
        <button
          type="button"
          onClick={handleImportResume}
          disabled={importing || !resumeText.trim()}
          className="btn-outline w-full mt-3 disabled:opacity-50"
        >
          {importing ? 'Analyzing resume...' : 'Import Resume'}
        </button>
        {importSuccess && (
          <p className="text-green-600 text-sm mt-2 text-center">
            Resume imported successfully!
          </p>
        )}
      </div>

      <div className="text-center text-gray-400 text-sm">— or fill in manually —</div>

      {/* Manual entry */}
      <div className="space-y-4">
        <div>
          <label htmlFor="fullName" className="label">
            Full Name
          </label>
          <input
            id="fullName"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            onBlur={handleSave}
            className="input"
            placeholder="John Doe"
          />
        </div>

        <div>
          <label htmlFor="title" className="label">
            Professional Title
          </label>
          <input
            id="title"
            type="text"
            value={professionalTitle}
            onChange={(e) => setProfessionalTitle(e.target.value)}
            onBlur={handleSave}
            className="input"
            placeholder="Senior Full-Stack Developer"
          />
        </div>

        <div>
          <label htmlFor="bio" className="label">
            Professional Summary
          </label>
          <textarea
            id="bio"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            onBlur={handleSave}
            className="input min-h-[100px]"
            placeholder="A brief overview of your experience and expertise..."
          />
        </div>

        <div>
          <label htmlFor="closing" className="label">
            Cover Letter Closing
          </label>
          <textarea
            id="closing"
            value={preferredClosing}
            onChange={(e) => setPreferredClosing(e.target.value)}
            onBlur={handleSave}
            className="input min-h-[60px]"
            placeholder="Best regards,&#10;John Doe"
          />
          <p className="text-xs text-gray-500 mt-1">
            This will be added to the end of every cover letter
          </p>
        </div>
      </div>
    </div>
  );
}
