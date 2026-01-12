/**
 * Zustand store for sidebar state management.
 */
import { create } from 'zustand';
import { apiClient, Profile, JobAnalysisResponse } from '../lib/api-client';

interface ScreeningQuestion {
  question: string;
  inputSelector: string;
}

interface JobData {
  url: string;
  title: string | null;
  description: string | null;
  budgetType: string | null;
  budgetAmount: string | null;
  skills: string[];
  experienceLevel: string | null;
  projectLength: string | null;
  screeningQuestions?: ScreeningQuestion[];
  clientInfo: {
    rating: string | null;
    location: string | null;
    totalSpent: string | null;
    hireRate: string | null;
  };
}

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

  // Generated cover letter
  coverLetter: string | null;
  coverLetterLoading: boolean;

  // UI
  currentView: 'auth' | 'setup' | 'generator' | 'memories' | 'history' | 'analytics';
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
  generateCoverLetter: () => Promise<void>;
  fillCoverLetter: () => Promise<boolean>;
  fillScreeningQuestion: (selector: string, answer: string) => Promise<boolean>;
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
  coverLetter: null,
  coverLetterLoading: false,
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
      set({ currentJob: job, jobAnalysis: null, coverLetter: null });
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

    set({ analysisLoading: true });
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
      set({ analysisLoading: false });
    }
  },

  // Generate cover letter
  generateCoverLetter: async () => {
    const { currentJob } = get();
    if (!currentJob || !currentJob.title || !currentJob.description) {
      return;
    }

    set({ coverLetterLoading: true });
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
      });
      set({ coverLetter: result.content, coverLetterLoading: false });
    } catch (error) {
      console.error('Generation error:', error);
      set({ coverLetterLoading: false });
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
