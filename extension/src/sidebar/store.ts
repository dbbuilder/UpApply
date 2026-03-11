/**
 * Zustand store for sidebar state management.
 */
import { create } from 'zustand';
import { apiClient, Profile, JobAnalysisResponse, ApplicationOutcome } from '../lib/api-client';
import type { JobData } from '../types';

interface User {
  id: string;
  email: string;
  has_profile: boolean;
}

interface AppState {
  // Auth
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;

  // Profile
  profile: Profile | null;
  profileLoading: boolean;

  // Current job
  currentJob: JobData | null;
  jobAnalysis: JobAnalysisResponse | null;
  analysisLoading: boolean;
  analysisError: string | null;

  // Generated cover letter
  coverLetter: string | null;
  coverLetterId: string | null;
  coverLetterLoading: boolean;
  coverLetterError: string | null;

  // Job tracking
  savedJobId: string | null;
  applicationId: string | null;

  // UI
  currentView: 'auth' | 'setup' | 'generator' | 'me' | 'find' | 'track' | 'go' | 'memories' | 'history' | 'analytics' | 'feedback' | 'skills' | 'profile';
  setupStep: number;

  // Actions
  setIsLoading: (loading: boolean) => void;
  setUser: (user: User | null) => void;
  setProfile: (profile: Profile | null) => void;
  setCurrentJob: (job: JobData | null) => void;
  setJobAnalysis: (analysis: JobAnalysisResponse | null) => void;
  setCoverLetter: (letter: string | null) => void;
  setCurrentView: (view: AppState['currentView']) => void;
  setSetupStep: (step: number) => void;

  // Async actions
  checkAuth: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  loadProfile: () => Promise<void>;
  analyzeCurrentJob: () => Promise<void>;
  generateCoverLetter: (inclusions?: string, prototypeUrl?: string, includeCallOffer?: boolean) => Promise<void>;
  regenerateCoverLetter: (feedback?: string, includeCallOffer?: boolean) => Promise<void>;
  fillCoverLetter: () => Promise<boolean>;
  fillScreeningQuestion: (selector: string, answer: string) => Promise<boolean>;
  saveCurrentJob: () => Promise<string | null>;
  createApplication: (bidAmount?: number) => Promise<boolean>;
  updateApplicationOutcome: (id: string, data: ApplicationOutcome) => Promise<boolean>;
  addSkillToProfile: (skillName: string, level?: string) => Promise<boolean>;
  removeSkillFromProfile: (skillName: string) => Promise<boolean>;
  updateSkillInProfile: (skillName: string, level: string, years?: number) => Promise<boolean>;
}

export const useAppStore = create<AppState>((set, get) => ({
  // Initial state
  isAuthenticated: false,
  isLoading: true,
  user: null,
  profile: null,
  profileLoading: false,
  currentJob: null,
  jobAnalysis: null,
  analysisLoading: false,
  analysisError: null,
  coverLetter: null,
  coverLetterId: null,
  coverLetterLoading: false,
  coverLetterError: null,
  savedJobId: null,
  applicationId: null,
  currentView: 'auth',
  setupStep: 1,

  // Simple setters
  setIsLoading: (loading) => set({ isLoading: loading }),
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setProfile: (profile) => set({ profile }),
  setCurrentJob: (job) => {
    const { currentJob } = get();
    // Only reset analysis/letter if it's a different job (different URL)
    if (currentJob?.url !== job?.url) {
      set({
        currentJob: job,
        jobAnalysis: null,
        coverLetter: null,
        coverLetterId: null,
        savedJobId: null,
        applicationId: null,
        analysisError: null,
        coverLetterError: null,
      });
    } else {
      // Same job, just update the data without resetting generated content
      set({ currentJob: job });
    }
  },
  setJobAnalysis: (analysis) => set({ jobAnalysis: analysis }),
  setCoverLetter: (letter) => set({ coverLetter: letter }),
  setCurrentView: (view) => set({ currentView: view }),
  setSetupStep: (step) => set({ setupStep: step }),

  // Check authentication status
  checkAuth: async () => {
    set({ isLoading: true });
    try {
      const token = await apiClient.getToken();
      if (!token) {
        set({ isAuthenticated: false, user: null, isLoading: false, currentView: 'auth' });
        return;
      }

      const user = await apiClient.getCurrentUser();
      set({ isAuthenticated: true, user, isLoading: false });

      if (!user.has_profile) {
        set({ currentView: 'setup' });
      } else {
        set({ currentView: 'generator' });
      }

      // Load profile
      get().loadProfile();
    } catch {
      set({ isAuthenticated: false, user: null, isLoading: false, currentView: 'auth' });
      await apiClient.clearToken();
    }
  },

  // Login
  login: async (email, password) => {
    set({ isLoading: true });
    try {
      await apiClient.login(email, password);
      const user = await apiClient.getCurrentUser();
      set({ isAuthenticated: true, user, isLoading: false });

      if (!user.has_profile) {
        set({ currentView: 'setup' });
      } else {
        set({ currentView: 'generator' });
        get().loadProfile();
      }
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  // Register
  register: async (email, password) => {
    set({ isLoading: true });
    try {
      await apiClient.register(email, password);
      const user = await apiClient.getCurrentUser();
      set({ isAuthenticated: true, user, isLoading: false, currentView: 'setup' });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  // Logout
  logout: async () => {
    await apiClient.logout();
    set({
      isAuthenticated: false,
      user: null,
      profile: null,
      currentJob: null,
      jobAnalysis: null,
      coverLetter: null,
      coverLetterId: null,
      savedJobId: null,
      applicationId: null,
      analysisError: null,
      coverLetterError: null,
      currentView: 'auth',
    });
  },

  // Load profile
  loadProfile: async () => {
    set({ profileLoading: true });
    try {
      const profile = await apiClient.getProfile();
      set({ profile, profileLoading: false });

      if (!profile.setup_completed) {
        set({ currentView: 'setup', setupStep: profile.setup_step || 1 });
      }
    } catch {
      set({ profileLoading: false });
    }
  },

  // Analyze current job
  analyzeCurrentJob: async () => {
    const { currentJob } = get();
    if (!currentJob || !currentJob.title || !currentJob.description) {
      return;
    }

    set({ analysisLoading: true, analysisError: null });
    try {
      const analysis = await apiClient.analyzeJob({
        title: currentJob.title,
        description: currentJob.description,
        skills_required: currentJob.skills,
        budget_type: currentJob.budgetType || undefined,
        budget_amount: currentJob.budgetAmount || undefined,
        client_info: {
          rating: currentJob.clientInfo.rating ? parseFloat(currentJob.clientInfo.rating) : undefined,
          location: currentJob.clientInfo.location || undefined,
          hire_rate: currentJob.clientInfo.hireRate || undefined,
          total_spent: currentJob.clientInfo.totalSpent || undefined,
        },
      });
      set({ jobAnalysis: analysis, analysisLoading: false });
    } catch (error) {
      console.error('Analysis error:', error);
      const message = error instanceof TypeError
        ? 'Server unavailable. The API may be starting up (Render cold start can take ~30s). Please retry.'
        : error instanceof Error ? error.message : 'Analysis failed';
      set({ analysisLoading: false, analysisError: message });
    }
  },

  // Save current job to backend and get a job_id
  saveCurrentJob: async () => {
    const { currentJob, savedJobId } = get();
    if (savedJobId) return savedJobId;
    if (!currentJob || !currentJob.title || !currentJob.description) return null;

    try {
      const job = await apiClient.createJob({
        upwork_url: currentJob.url,
        title: currentJob.title,
        description: currentJob.description,
        skills_required: currentJob.skills,
        budget_type: currentJob.budgetType || undefined,
        budget_amount: currentJob.budgetAmount || undefined,
      });
      set({ savedJobId: job.id });
      return job.id;
    } catch (error) {
      console.error('Failed to save job:', error);
      return null;
    }
  },

  // Generate cover letter
  generateCoverLetter: async (inclusions?: string, prototypeUrl?: string, includeCallOffer: boolean = true) => {
    const { currentJob } = get();
    if (!currentJob || !currentJob.title || !currentJob.description) {
      return;
    }

    set({ coverLetterLoading: true, coverLetterError: null });
    try {
      const result = await apiClient.generateCoverLetter({
        job_data: {
          upwork_url: currentJob.url,
          title: currentJob.title,
          description: currentJob.description,
          skills_required: currentJob.skills,
          budget_type: currentJob.budgetType || undefined,
          budget_amount: currentJob.budgetAmount || undefined,
        },
        custom_instructions: inclusions || undefined,
        prototype_url: prototypeUrl || undefined,
        include_call_offer: includeCallOffer,
      });
      set({
        coverLetter: result.content,
        coverLetterId: result.id,
        savedJobId: result.job_id,
        coverLetterLoading: false,
      });
    } catch (error) {
      console.error('Generation error:', error);
      const message = error instanceof TypeError
        ? 'Server unavailable. The API may be starting up (Render cold start can take ~30s). Please retry.'
        : error instanceof Error ? error.message : 'Generation failed';
      set({ coverLetterLoading: false, coverLetterError: message });
    }
  },

  // Regenerate cover letter with optional feedback
  regenerateCoverLetter: async (feedback?: string, includeCallOffer: boolean = true) => {
    const { coverLetterId } = get();
    if (!coverLetterId) {
      // Fall back to fresh generation
      return get().generateCoverLetter(undefined, undefined, includeCallOffer);
    }

    set({ coverLetterLoading: true, coverLetterError: null });
    try {
      const result = await apiClient.regenerateCoverLetter(coverLetterId, feedback, includeCallOffer);
      set({
        coverLetter: result.content,
        coverLetterId: result.id,
        coverLetterLoading: false,
      });
    } catch (error) {
      console.error('Regeneration error:', error);
      const message = error instanceof Error ? error.message : 'Regeneration failed';
      set({ coverLetterLoading: false, coverLetterError: message });
    }
  },

  // Fill cover letter in page
  fillCoverLetter: async () => {
    const { coverLetter } = get();
    if (!coverLetter) return false;

    return new Promise((resolve) => {
      chrome.runtime.sendMessage(
        { type: 'FILL_COVER_LETTER', content: coverLetter },
        (response) => {
          resolve(response?.success || false);
        }
      );
    });
  },

  // Fill screening question in page
  fillScreeningQuestion: async (selector: string, answer: string) => {
    return new Promise<boolean>((resolve) => {
      chrome.runtime.sendMessage(
        { type: 'FILL_SCREENING_QUESTION', selector, answer },
        (response) => {
          resolve(response?.success || false);
        }
      );
    });
  },

  // Create application tracking record
  createApplication: async (bidAmount?: number) => {
    const { savedJobId, coverLetterId } = get();
    if (!savedJobId) return false;

    try {
      const app = await apiClient.createApplication({
        job_id: savedJobId,
        cover_letter_id: coverLetterId || undefined,
        bid_amount: bidAmount,
      });
      set({ applicationId: app.id });
      return true;
    } catch (error) {
      console.error('Failed to create application:', error);
      return false;
    }
  },

  // Update application outcome
  updateApplicationOutcome: async (id: string, data: ApplicationOutcome) => {
    try {
      await apiClient.updateApplicationOutcome(id, data);
      return true;
    } catch (error) {
      console.error('Failed to update outcome:', error);
      return false;
    }
  },

  // Add a skill to the user's profile
  addSkillToProfile: async (skillName: string, level: string = 'beginner') => {
    const { profile } = get();
    if (!profile) return false;

    const existingSkills = profile.skills || [];
    // Check if skill already exists (case-insensitive)
    if (existingSkills.some(s => s.name.toLowerCase() === skillName.toLowerCase())) {
      return false;
    }

    const updatedSkills = [...existingSkills, { name: skillName, level }];
    try {
      const updated = await apiClient.updateProfile({ skills: updatedSkills });
      set({ profile: updated });
      return true;
    } catch (error) {
      console.error('Failed to add skill:', error);
      return false;
    }
  },

  // Remove a skill from the user's profile
  removeSkillFromProfile: async (skillName: string) => {
    const { profile } = get();
    if (!profile) return false;

    const existingSkills = profile.skills || [];
    const updatedSkills = existingSkills.filter(
      s => s.name.toLowerCase() !== skillName.toLowerCase()
    );

    try {
      const updated = await apiClient.updateProfile({ skills: updatedSkills });
      set({ profile: updated });
      return true;
    } catch (error) {
      console.error('Failed to remove skill:', error);
      return false;
    }
  },

  // Update a skill's level/years in the profile
  updateSkillInProfile: async (skillName: string, level: string, years?: number) => {
    const { profile } = get();
    if (!profile) return false;

    const existingSkills = profile.skills || [];
    const updatedSkills = existingSkills.map(s =>
      s.name.toLowerCase() === skillName.toLowerCase()
        ? { ...s, level, years }
        : s
    );

    try {
      const updated = await apiClient.updateProfile({ skills: updatedSkills });
      set({ profile: updated });
      return true;
    } catch (error) {
      console.error('Failed to update skill:', error);
      return false;
    }
  },
}));

// Listen for job data updates from background script
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'JOB_DATA_UPDATED') {
    useAppStore.getState().setCurrentJob(message.data);
    // Auto-analyze if authenticated
    if (useAppStore.getState().isAuthenticated) {
      useAppStore.getState().analyzeCurrentJob();
    }
  }
});

// Load current job from storage on init
chrome.storage.local.get('currentJob', (result) => {
  if (result.currentJob) {
    useAppStore.getState().setCurrentJob(result.currentJob);
  }
});
