/**
 * API client for communicating with the UpApply backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://upapply-api.onrender.com';

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
}

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.loadToken();
  }

  private async loadToken() {
    const result = await chrome.storage.local.get('authToken');
    this.token = result.authToken || null;
  }

  async setToken(token: string) {
    this.token = token;
    await chrome.storage.local.set({ authToken: token });
  }

  async clearToken() {
    this.token = null;
    await chrome.storage.local.remove('authToken');
  }

  async getToken(): Promise<string | null> {
    if (!this.token) {
      await this.loadToken();
    }
    return this.token;
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {} } = options;

    const token = await this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (body) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new ApiError(response.status, error.detail || 'Request failed');
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  // Auth
  async register(email: string, password: string) {
    const result = await this.request<{ access_token: string }>('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password },
    });
    await this.setToken(result.access_token);
    return result;
  }

  async login(email: string, password: string) {
    const result = await this.request<{ access_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    await this.setToken(result.access_token);
    return result;
  }

  async getCurrentUser() {
    return this.request<{
      id: string;
      email: string;
      is_active: boolean;
      is_verified: boolean;
      has_profile: boolean;
    }>('/api/v1/auth/me');
  }

  async logout() {
    await this.clearToken();
  }

  // Profile
  async getProfile() {
    return this.request<Profile>('/api/v1/profile');
  }

  async updateProfile(data: Partial<Profile>) {
    return this.request<Profile>('/api/v1/profile', {
      method: 'PUT',
      body: data,
    });
  }

  async updateGoals(data: ProfileGoals) {
    return this.request<Profile>('/api/v1/profile/goals', {
      method: 'PUT',
      body: data,
    });
  }

  async updatePreferences(data: ProfilePreferences) {
    return this.request<Profile>('/api/v1/profile/preferences', {
      method: 'PUT',
      body: data,
    });
  }

  async updateDealbreakers(data: ProfileDealbreakers) {
    return this.request<Profile>('/api/v1/profile/dealbreakers', {
      method: 'PUT',
      body: data,
    });
  }

  async updatePricing(data: ProfilePricing) {
    return this.request<Profile>('/api/v1/profile/pricing', {
      method: 'PUT',
      body: data,
    });
  }

  async importResume(resumeText: string) {
    return this.request<ResumeImportResponse>('/api/v1/profile/import-resume', {
      method: 'POST',
      body: { resume_text: resumeText },
    });
  }

  async completeSetup() {
    return this.request<Profile>('/api/v1/profile/complete-setup', {
      method: 'POST',
    });
  }

  // Memories
  async getMemories(category?: string) {
    const params = category ? `?category=${category}` : '';
    return this.request<Memory[]>(`/api/v1/memories${params}`);
  }

  async createMemory(data: MemoryCreate) {
    return this.request<Memory>('/api/v1/memories', {
      method: 'POST',
      body: data,
    });
  }

  async updateMemory(id: string, data: Partial<MemoryCreate>) {
    return this.request<Memory>(`/api/v1/memories/${id}`, {
      method: 'PUT',
      body: data,
    });
  }

  async deleteMemory(id: string) {
    return this.request<void>(`/api/v1/memories/${id}`, {
      method: 'DELETE',
    });
  }

  async searchMemories(query: string, limit = 10) {
    return this.request<MemorySearchResult[]>('/api/v1/memories/search', {
      method: 'POST',
      body: { query, limit },
    });
  }

  async bulkImportMemories(memories: MemoryCreate[]) {
    return this.request<Memory[]>('/api/v1/memories/bulk-import', {
      method: 'POST',
      body: { memories },
    });
  }

  // Jobs
  async analyzeJob(data: JobAnalysisRequest) {
    return this.request<JobAnalysisResponse>('/api/v1/jobs/analyze', {
      method: 'POST',
      body: data,
    });
  }

  async createJob(data: JobCreate) {
    return this.request<Job>('/api/v1/jobs', {
      method: 'POST',
      body: data,
    });
  }

  async getJobs(minScore?: number) {
    const params = minScore ? `?min_score=${minScore}` : '';
    return this.request<Job[]>(`/api/v1/jobs${params}`);
  }

  async getJob(id: string) {
    return this.request<Job>(`/api/v1/jobs/${id}`);
  }

  async getJobMatch(id: string) {
    return this.request<JobAnalysisResponse>(`/api/v1/jobs/${id}/match`);
  }

  // Cover Letters
  async generateCoverLetter(data: CoverLetterGenerateRequest) {
    return this.request<CoverLetter>('/api/v1/jobs/cover-letters/generate', {
      method: 'POST',
      body: data,
    });
  }

  async getCoverLetters(jobId?: string) {
    const params = jobId ? `?job_id=${jobId}` : '';
    return this.request<CoverLetter[]>(`/api/v1/jobs/cover-letters${params}`);
  }

  async regenerateCoverLetter(id: string, feedback?: string) {
    return this.request<CoverLetter>(`/api/v1/jobs/cover-letters/${id}/regenerate`, {
      method: 'POST',
      body: { feedback },
    });
  }

  // Applications
  async createApplication(data: ApplicationCreate) {
    return this.request<Application>('/api/v1/applications', {
      method: 'POST',
      body: data,
    });
  }

  async getApplications() {
    return this.request<Application[]>('/api/v1/applications');
  }

  async getApplicationStats() {
    return this.request<ApplicationStats>('/api/v1/applications/stats');
  }

  async updateApplicationOutcome(id: string, data: ApplicationOutcome) {
    return this.request<Application>(`/api/v1/applications/${id}/outcome`, {
      method: 'PUT',
      body: data,
    });
  }

  // Feedback
  async submitFeedback(data: FeedbackCreate) {
    return this.request<Feedback>('/api/v1/feedback', {
      method: 'POST',
      body: data,
    });
  }

  async getAnalyticsDashboard() {
    return this.request<AnalyticsDashboard>('/api/v1/feedback/analytics/dashboard');
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

// Types
export interface Profile {
  id: string;
  user_id: string;
  full_name?: string;
  professional_title?: string;
  headline?: string;
  bio?: string;
  resume_text?: string;
  skills?: { name: string; level?: string; years?: number }[];
  work_history?: { title: string; company: string; duration?: string; highlights?: string[] }[];
  education?: { degree: string; institution: string; year?: number }[];
  certifications?: string[];
  portfolio_links?: string[];
  career_goals?: string;
  ideal_project_description?: string;
  skills_to_highlight?: string[];
  skills_to_develop?: string[];
  preferred_project_types?: string[];
  preferred_industries?: string[];
  preferred_team_size?: string;
  preferred_client_types?: string[];
  project_duration_preference?: string;
  avoid_keywords?: string[];
  avoid_industries?: string[];
  minimum_budget?: number;
  minimum_hourly_rate?: number;
  red_flag_patterns?: string[];
  tone_preference?: string;
  communication_style?: string;
  timezone?: string;
  preferred_closing?: string;
  unique_strengths?: string[];
  hourly_rate_min?: number;
  hourly_rate_max?: number;
  hourly_rate_preferred?: number;
  fixed_price_minimum?: number;
  hours_per_week_available?: number;
  currently_accepting_work?: boolean;
  setup_completed: boolean;
  setup_step?: number;
}

export interface ProfileGoals {
  career_goals?: string;
  ideal_project_description?: string;
  skills_to_highlight?: string[];
  skills_to_develop?: string[];
}

export interface ProfilePreferences {
  preferred_project_types?: string[];
  preferred_industries?: string[];
  preferred_team_size?: string;
  preferred_client_types?: string[];
  project_duration_preference?: string;
}

export interface ProfileDealbreakers {
  avoid_keywords?: string[];
  avoid_industries?: string[];
  minimum_budget?: number;
  minimum_hourly_rate?: number;
  red_flag_patterns?: string[];
}

export interface ProfilePricing {
  hourly_rate_min?: number;
  hourly_rate_max?: number;
  hourly_rate_preferred?: number;
  fixed_price_minimum?: number;
  hours_per_week_available?: number;
  currently_accepting_work?: boolean;
}

export interface ResumeImportResponse {
  full_name?: string;
  professional_title?: string;
  bio?: string;
  skills?: { name: string; level?: string; years?: number }[];
  work_history?: { title: string; company: string; duration?: string; highlights?: string[] }[];
  education?: { degree: string; institution: string; year?: number }[];
  certifications?: string[];
  extracted_memories?: MemoryCreate[];
}

export interface Memory {
  id: string;
  user_id: string;
  title: string;
  content: string;
  category?: string;
  skills_demonstrated?: string[];
  industry?: string;
  project_type?: string;
  outcome?: string;
  metrics?: Record<string, unknown>;
  importance_score?: number;
  created_at: string;
}

export interface MemoryCreate {
  title: string;
  content: string;
  category?: string;
  skills_demonstrated?: string[];
  industry?: string;
  project_type?: string;
  outcome?: string;
  metrics?: Record<string, unknown>;
  importance_score?: number;
}

export interface MemorySearchResult {
  memory: Memory;
  similarity: number;
}

export interface JobAnalysisRequest {
  title: string;
  description: string;
  skills_required?: string[];
  budget_type?: string;
  budget_amount?: string;
  client_info?: {
    rating?: number;
    location?: string;
    hire_rate?: string;
    total_spent?: string;
  };
}

export interface JobAnalysisResponse {
  match_score: number;
  skill_matches: { skill: string; match_type: string; user_level?: string; relevance_score: number }[];
  missing_skills: string[];
  strengths: string[];
  concerns: string[];
  deal_breaker_warnings: string[];
  relevant_memories: Record<string, unknown>[];
  recommendation: string;
}

export interface JobCreate {
  upwork_url: string;
  title: string;
  description: string;
  budget_type?: string;
  budget_amount?: string;
  budget_min?: number;
  budget_max?: number;
  skills_required?: string[];
  experience_level?: string;
  project_length?: string;
  client_info?: {
    rating?: number;
    location?: string;
    hire_rate?: string;
    total_spent?: string;
  };
}

export interface Job {
  id: string;
  user_id: string;
  upwork_url: string;
  title: string;
  description: string;
  match_score?: number;
  analysis?: JobAnalysisResponse;
  created_at: string;
}

export interface CoverLetterGenerateRequest {
  job_id?: string;
  job_data?: JobCreate;
}

export interface CoverLetter {
  id: string;
  user_id: string;
  job_id: string;
  content: string;
  model_used: string;
  memories_used?: string[];
  word_count?: number;
  version: number;
  match_score?: number;
  highlighted_skills?: string[];
  created_at: string;
}

export interface ApplicationCreate {
  job_id: string;
  cover_letter_id?: string;
  bid_amount?: number;
}

export interface Application {
  id: string;
  user_id: string;
  job_id: string;
  status: string;
  bid_amount?: number;
  earnings?: number;
  client_response?: string;
  outcome_notes?: string;
  submitted_at?: string;
  responded_at?: string;
  outcome_recorded_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ApplicationStats {
  total_applications: number;
  submitted: number;
  viewed: number;
  responded: number;
  hired: number;
  declined: number;
  response_rate: number;
  success_rate: number;
  total_earnings: number;
}

export interface ApplicationOutcome {
  status: string;
  outcome_notes?: string;
  client_response?: string;
  earnings?: number;
}

export interface FeedbackCreate {
  application_id?: string;
  cover_letter_id?: string;
  feedback_type: string;
  rating?: number;
  comment?: string;
  was_helpful?: boolean;
}

export interface Feedback {
  id: string;
  feedback_type: string;
  rating?: number;
  comment?: string;
  created_at: string;
}

export interface AnalyticsDashboard {
  total_applications: number;
  response_rate: number;
  interview_rate: number;
  hire_rate: number;
  avg_match_score?: number;
  avg_time_to_response_days?: number;
  top_skills: { skill: string; success_rate: number; applications: number }[];
  weekly_applications: { week: string; applications: number; responses: number }[];
  insights: { type: string; message: string; confidence: number }[];
}

export const apiClient = new ApiClient(API_BASE_URL);
