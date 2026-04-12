/**
 * API client for communicating with the UpApply backend.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://upapply-api.onrender.com';

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
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

  async importChatGPTConversations(file: File): Promise<{
    memories_imported: number;
    proposals_imported: number;
    conversations_processed: number;
    skipped: number;
  }> {
    const stored = await chrome.storage.local.get('authToken');
    const token = stored.authToken as string | undefined;
    const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
    const formData = new FormData();
    formData.append('file', file);
    const resp = await fetch(`${apiBase}/api/v1/import/import-chatgpt-conversations`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });
    if (!resp.ok) throw new Error(`API ${resp.status}`);
    return resp.json();
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

  async getJobs(minScore?: number, source?: string, isSaved?: boolean) {
    const p = new URLSearchParams();
    if (minScore !== undefined) p.set('min_score', String(minScore));
    if (source) p.set('source', source);
    if (isSaved !== undefined) p.set('is_saved', String(isSaved));
    const qs = p.toString();
    return this.request<Job[]>(`/api/v1/jobs${qs ? `?${qs}` : ''}`);
  }

  async importBulkJobs(jobs: JobImportItem[], source: 'saved' | 'search', searchQuery?: string, searchQueryId?: string) {
    return this.request<Job[]>('/api/v1/jobs/import-bulk', {
      method: 'POST',
      body: { jobs, source, search_query: searchQuery, search_query_id: searchQueryId },
    });
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

  async regenerateCoverLetter(id: string, feedback?: string, includeCallOffer: boolean = true) {
    return this.request<CoverLetter>(`/api/v1/jobs/cover-letters/${id}/regenerate`, {
      method: 'POST',
      body: { feedback, include_call_offer: includeCallOffer },
    });
  }

  async submitCoverLetter(id: string, submittedText: string) {
    return this.request<CoverLetter>(`/api/v1/jobs/cover-letters/${id}/submit`, {
      method: 'PUT',
      body: { submitted_text: submittedText },
    });
  }

  async improveCoverLetter(id: string) {
    return this.request<{
      cover_letter_id: string;
      improved_content: string;
      improvement_notes: string[];
      hired_examples_used: number;
    }>(`/api/v1/jobs/cover-letters/${id}/improve`, { method: 'POST' });
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

  // Screening Answers
  async createScreeningAnswer(data: ScreeningAnswerCreate) {
    return this.request<ScreeningAnswer>('/api/v1/screening-answers', {
      method: 'POST',
      body: data,
    });
  }

  async searchScreeningAnswers(question: string, limit = 5) {
    return this.request<ScreeningAnswerSearchResult[]>('/api/v1/screening-answers/search', {
      method: 'POST',
      body: { question, limit },
    });
  }

  async generateScreeningAnswer(question: string, jobTitle?: string, jobDescription?: string, jobSkills?: string[]) {
    return this.request<{ answer: string }>('/api/v1/screening-answers/generate', {
      method: 'POST',
      body: { question, job_title: jobTitle, job_description: jobDescription, job_skills: jobSkills },
    });
  }

  async bulkCreateScreeningAnswers(answers: ScreeningAnswerCreate[]) {
    return this.request<ScreeningAnswer[]>('/api/v1/screening-answers/bulk', {
      method: 'POST',
      body: { answers },
    });
  }

  async suggestMilestones(
    jobTitle: string,
    jobDescription: string,
    budgetAmount?: string,
    numMilestones: number = 3
  ): Promise<{ milestones: MilestoneSuggestion[] }> {
    return this.request('/api/v1/jobs/suggest-milestones', {
      method: 'POST',
      body: {
        job_title: jobTitle,
        job_description: jobDescription,
        budget_amount: budgetAmount,
        num_milestones: numMilestones,
      },
    });
  }

  // Proposals
  async createProposal(data: ProposalCreate) {
    return this.request<Proposal>('/api/v1/proposals', {
      method: 'POST',
      body: data,
    });
  }

  async getProposals(params?: { status?: string; was_hired?: boolean; limit?: number }) {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append('status', params.status);
    if (params?.was_hired !== undefined) searchParams.append('was_hired', String(params.was_hired));
    if (params?.limit) searchParams.append('limit', String(params.limit));
    const query = searchParams.toString() ? `?${searchParams}` : '';
    return this.request<Proposal[]>(`/api/v1/proposals${query}`);
  }

  async searchProposals(query: string, limit = 5, includeSuccessfulOnly = false) {
    return this.request<ProposalSearchResult[]>('/api/v1/proposals/search', {
      method: 'POST',
      body: { query, limit, include_successful_only: includeSuccessfulOnly },
    });
  }

  async bulkCreateProposals(proposals: ProposalCreate[]) {
    return this.request<Proposal[]>('/api/v1/proposals/bulk', {
      method: 'POST',
      body: { proposals },
    });
  }

  async importProposalsFromUpwork(proposals: Record<string, unknown>[]) {
    return this.request<Proposal[]>('/api/v1/proposals/import-from-upwork', {
      method: 'POST',
      body: { proposals },
    });
  }

  async updateProposal(id: string, data: Partial<ProposalCreate> & { was_hired?: boolean; client_responded?: boolean }) {
    return this.request<Proposal>(`/api/v1/proposals/${id}`, {
      method: 'PUT',
      body: data,
    });
  }

  async getProposalStats() {
    return this.request<ProposalStats>('/api/v1/proposals/stats');
  }

  async getProposalInsights() {
    return this.request<{
      insights: {
        whats_working: string;
        whats_not_landing: string;
        recommendations: string[];
        job_types_to_target: string[];
        job_types_to_avoid: string[];
        positioning_tip: string;
      } | null;
      proposal_count?: number;
      response_rate?: number;
      message?: string;
    }>('/api/v1/proposals/insights');
  }

  // Attachment extraction
  async extractJobAttachments(
    jobId: string,
    attachments: AttachmentData[],
    fullDescription?: string
  ) {
    return this.request<ExtractAttachmentsResponse>(`/api/v1/jobs/${jobId}/extract-attachments`, {
      method: 'POST',
      body: { attachments, full_description: fullDescription },
    });
  }

  // Beta Feedback (no auth required)
  async submitBetaFeedback(data: BetaFeedbackCreate) {
    return this.request<BetaFeedbackResponse>('/api/v1/beta-feedback', {
      method: 'POST',
      body: data,
    });
  }

  // Search Queries
  async getSearchQueries() {
    return this.request<SearchQuery[]>('/api/v1/search-queries');
  }

  async createSearchQuery(query: string, urlParams?: string, source?: string) {
    return this.request<SearchQuery>('/api/v1/search-queries', {
      method: 'POST',
      body: { query, url_params: urlParams, source },
    });
  }

  async deleteSearchQuery(id: string) {
    return this.request<void>(`/api/v1/search-queries/${id}`, { method: 'DELETE' });
  }

  async seedSearchQueries() {
    return this.request<SearchQuery[]>('/api/v1/search-queries/seed', { method: 'POST' });
  }

  async generateSearchQueries() {
    return this.request<SearchQuery[]>('/api/v1/search-queries/generate', { method: 'POST' });
  }

  async recordQueryRun(id: string, stats: { jobs_found: number; avg_score: number; high_score_count: number }) {
    return this.request<SearchQuery>(`/api/v1/search-queries/${id}/record-run`, {
      method: 'POST',
      body: stats,
    });
  }

  async bulkImportSearchQueries(queries: Array<{ query: string; url_params?: string; source?: string }>) {
    return this.request<SearchQuery[]>('/api/v1/search-queries/bulk-import', {
      method: 'POST',
      body: { queries },
    });
  }

  async evaluateSearchLab() {
    return this.request<SearchLabResult>('/api/v1/search-queries/evaluate', { method: 'POST' });
  }

  async optimizeSearchLab(experiments: QueryExperimentData[]) {
    return this.request<OptimizeResult>('/api/v1/search-queries/optimize', {
      method: 'POST',
      body: { experiments },
    });
  }

  // Job Reviews
  async upsertJobReview(data: {
    upwork_job_url: string;
    job_title: string;
    ai_score?: number;
    chips?: string[];
    budget_amount?: string | null;
    budget_type?: string | null;
    scored_at?: string;
  }) {
    return this.request<JobReview>('/api/v1/job-reviews', {
      method: 'POST',
      body: data,
    });
  }

  async listJobReviews(params?: { sort?: string; min_score?: number; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.sort) qs.set('sort', params.sort);
    if (params?.min_score != null) qs.set('min_score', String(params.min_score));
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return this.request<JobReviewListResponse>(`/api/v1/job-reviews${q ? `?${q}` : ''}`);
  }

  async rateJobReview(id: string, data: JobReviewRateRequest) {
    return this.request<JobReview>(`/api/v1/job-reviews/${id}/rate`, {
      method: 'PATCH',
      body: data,
    });
  }

  // Active Contracts (imported contracts still open on Upwork)
  async getActiveContracts() {
    return this.request<Job[]>('/api/v1/jobs/active-contracts');
  }

  // Work Logs
  async createWorkLog(data: WorkLogCreate) {
    return this.request<WorkLog>('/api/v1/work-logs', {
      method: 'POST',
      body: data,
    });
  }

  async listWorkLogs(params?: { job_id?: string; limit?: number }) {
    const qs = new URLSearchParams();
    if (params?.job_id) qs.set('job_id', params.job_id);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return this.request<WorkLogListResponse>(`/api/v1/work-logs${q ? `?${q}` : ''}`);
  }

  async updateWorkLog(id: string, data: WorkLogUpdate) {
    return this.request<WorkLog>(`/api/v1/work-logs/${id}`, {
      method: 'PATCH',
      body: data,
    });
  }

  async deleteWorkLog(id: string) {
    return this.request<void>(`/api/v1/work-logs/${id}`, { method: 'DELETE' });
  }

  async extractWorkImage(imageBase64: string, filename?: string) {
    return this.request<{ extracted_text: string; summary: string }>('/api/v1/work-logs/extract-image', {
      method: 'POST',
      body: { image_base64: imageBase64, filename },
    });
  }

  // Profile Optimization
  async getProfileOptimization(forceRefresh = false): Promise<ProfileOptimizeResponse> {
    const qs = forceRefresh ? '?force_refresh=true' : '';
    return this.request<ProfileOptimizeResponse>(`/api/v1/profile/optimize${qs}`, {
      method: 'POST',
    });
  }

  // Applications / Proposals corpus backfill
  async backfillProposalsCorpus(): Promise<{ created: number; updated: number; skipped: number }> {
    return this.request('/api/v1/applications/backfill-proposals', { method: 'POST' });
  }

  // Job Queue (agent suggestions)
  async getJobQueue(statusFilter?: string): Promise<JobQueueItem[]> {
    const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : '';
    return this.request<JobQueueItem[]>(`/api/v1/job-queue${qs}`);
  }

  async actionJobQueueItem(
    id: string,
    action: 'approve' | 'reject',
    rejectionReason?: string
  ): Promise<JobQueueItem> {
    return this.request<JobQueueItem>(`/api/v1/job-queue/${id}/action`, {
      method: 'PUT',
      body: { action, rejection_reason: rejectionReason },
    });
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
  preferred_client_locations?: string[];
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
  preferred_client_locations?: string[];
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
  upwork_job_id?: string;
  title: string;
  description: string;
  skills_required?: string[];
  experience_level?: string;
  budget_type?: string;
  budget_amount?: string;
  client_info?: Record<string, unknown>;
  match_score?: number;
  analysis?: JobAnalysisResponse;
  is_saved?: boolean;
  source?: string;
  expires_at?: string;
  scraped_at: string;
  created_at: string;
}

export interface JobImportItem {
  upwork_job_id: string;
  upwork_url: string;
  title: string;
  description: string;
  job_type?: string;
  experience_level?: string;
  posted_date_raw?: string;
  client_info?: Record<string, unknown>;
  skills?: string[];
}

export interface CoverLetterGenerateRequest {
  job_id?: string;
  job_data?: JobCreate;
  custom_instructions?: string;
  prototype_url?: string;
  include_call_offer?: boolean;
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

// Screening Answer Types
export interface ScreeningAnswerCreate {
  question: string;
  answer: string;
  question_type?: string;
  job_id?: string;
  application_id?: string;
  job_title?: string;
  job_skills?: string[];
}

export interface ScreeningAnswer {
  id: string;
  user_id: string;
  job_id?: string;
  application_id?: string;
  question: string;
  answer: string;
  question_type?: string;
  job_title?: string;
  was_successful?: boolean;
  created_at: string;
}

export interface ScreeningAnswerSearchResult {
  answer: ScreeningAnswer;
  similarity: number;
}

// Proposal Types
export interface ProposalCreate {
  cover_letter_text: string;
  job_id?: string;
  upwork_proposal_id?: string;
  upwork_job_url?: string;
  job_title?: string;
  job_description_snippet?: string;
  job_skills?: string[];
  job_budget?: string;
  job_category?: string;
  bid_amount?: number;
  bid_type?: string;
  status?: string;
  submitted_at?: string;
  source?: string;
}

export interface Proposal {
  id: string;
  user_id: string;
  job_id?: string;
  upwork_proposal_id?: string;
  upwork_job_url?: string;
  cover_letter_text: string;
  job_title?: string;
  job_description_snippet?: string;
  job_skills?: string[];
  job_budget?: string;
  job_category?: string;
  bid_amount?: number;
  bid_type?: string;
  status?: string;
  was_hired?: boolean;
  client_responded?: boolean;
  earnings?: number;
  source: string;
  submitted_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ProposalSearchResult {
  proposal: Proposal;
  similarity: number;
}

export interface ProposalStats {
  total_proposals: number;
  hired: number;
  responded: number;
  interviewed: number;
  total_earnings: number;
  submitted: number;
  viewed: number;
  scored_count: number;
  hire_rate: number;
  response_rate: number;
  avg_days_to_response?: number;
}

// Attachment Extraction Types
export interface AttachmentData {
  data: string;  // Base64-encoded file content
  filename: string;
  content_type: string;
}

export interface AttachmentMetadata {
  filename: string;
  content_type: string;
  size: number;
  extraction_status: string;
  error?: string;
}

export interface ExtractAttachmentsResponse {
  job_id: string;
  attachment_text: string;
  full_description?: string;
  attachment_count: number;
  attachment_metadata: AttachmentMetadata[];
  extraction_errors: string[];
}

// Beta Feedback Types
export interface BetaFeedbackCreate {
  feedback_type: 'bug' | 'feature_request' | 'usability' | 'general';
  description: string;
  email?: string;
  page_url?: string;
  extension_version?: string;
  browser_info?: string;
}

export interface BetaFeedbackResponse {
  id: string;
  feedback_type: string;
  description: string;
  email?: string;
  page_url?: string;
  extension_version?: string;
  created_at: string;
}

// Milestone Types
export interface MilestoneSuggestion {
  description: string;
  days_from_start: number;
  amount: number;
}

// Search Query Types
export interface SearchQuery {
  id: string;
  query: string;
  url_params?: string;
  source: string;
  active: boolean;
  run_count: number;
  last_run_at?: string;
  total_jobs_found: number;
  avg_match_score?: number;
  high_score_count: number;
  performance_score: number;
  is_stale: boolean;
  is_low_performer: boolean;
  created_at: string;
}

export interface QueryCoverage {
  query_id: string;
  query: string;
  url_params?: string;
  coverage_count: number;
  coverage_pct: number;
  sample_matches: string[];
}

export interface SuggestedQuery {
  query: string;
  url_params: string;
  reasoning: string;
  gap_jobs_targeted: string[];
}

export interface SearchLabResult {
  total_target_jobs: number;
  covered_count: number;
  coverage_pct: number;
  query_coverage: QueryCoverage[];
  gap_jobs: string[];
  suggestions: SuggestedQuery[];
  evaluated_at: string;
}

export interface QueryExperimentData {
  query_id: string;
  query: string;
  url_params?: string;
  jobs_returned: number;
  avg_score: number;
  high_score_count: number;
  sample_good_titles?: string[];
  sample_bad_titles?: string[];
}

export interface QueryVariant {
  query: string;
  url_params: string;
  reasoning: string;
  change_type: string;  // "broader" | "narrower" | "reframe"
}

export interface QueryOptimization {
  query_id: string;
  original_query: string;
  grade: string;  // "strong" | "low_volume" | "low_quality" | "both"
  inclusive_score: number;
  variants: QueryVariant[];
}

export interface OptimizeResult {
  optimizations: QueryOptimization[];
  evaluated_at: string;
}

// Job Review Types
export interface JobReview {
  id: string;
  upwork_job_url: string;
  upwork_job_id?: string;
  job_title: string;
  ai_score?: number;
  chips?: string[];
  budget_amount?: string;
  budget_type?: string;
  user_rating?: number;
  user_comment?: string;
  scored_at?: string;
  created_at: string;
}

export interface JobReviewListResponse {
  reviews: JobReview[];
  total: number;
}

export interface JobReviewRateRequest {
  user_rating: number;
  user_comment?: string;
}

// Work Log Types
export interface WorkLogCreate {
  job_id?: string;
  contract_title: string;
  upwork_contract_id?: string;
  task_description: string;
  started_at?: string;   // ISO datetime
  ended_at?: string;
  duration_minutes?: number;
  attachment_filename?: string;
  attachment_text?: string;
  notes?: string;
}

export interface WorkLogUpdate {
  task_description?: string;
  started_at?: string;
  ended_at?: string;
  duration_minutes?: number;
  attachment_filename?: string;
  attachment_text?: string;
  notes?: string;
}

export interface WorkLog {
  id: string;
  user_id: string;
  job_id?: string;
  contract_title: string;
  upwork_contract_id?: string;
  task_description: string;
  started_at?: string;
  ended_at?: string;
  duration_minutes?: number;
  attachment_filename?: string;
  attachment_text?: string;
  notes?: string;
  created_at: string;
}

export interface WorkLogListResponse {
  logs: WorkLog[];
  total: number;
  total_minutes: number;
}

// Profile Optimization Types
export interface ProfileDimension {
  name: string;
  score: number;   // 0-100
  status: 'good' | 'warning' | 'critical';
  summary: string;
  detail: string;
}

export interface ProfileRecommendation {
  priority: 'critical' | 'high' | 'medium' | 'low';
  dimension: string;
  title: string;
  problem: string;
  action: string;
}

export interface May2026Item {
  item: string;
  done: boolean;
  note: string;
}

export interface ProfileOptimizeResponse {
  overall_score: number;
  dimensions: ProfileDimension[];
  recommendations: ProfileRecommendation[];
  suggested_title?: string;
  suggested_overview_hook?: string;
  suggested_skills?: string[];
  may_2026_checklist: May2026Item[];
  cached: boolean;
  cached_at?: string;
}

// ── Job Queue (agent suggestions) ──────────────────────────────────────────

export interface JobQueueItem {
  id: string;
  user_id: string;
  upwork_url: string;
  title: string;
  description?: string;
  skills?: string[];
  budget_amount?: string;
  budget_type?: string;
  client_info?: Record<string, unknown>;
  ai_score?: number;
  ai_reasoning?: string;
  chips?: string[];
  /** suggested | approved | rejected | applied | expired */
  status: string;
  source: string;
  source_query_id?: string;
  rejection_reason?: string;
  created_at: string;
  reviewed_at?: string;
  expires_at?: string;
}

export const apiClient = new ApiClient(API_BASE_URL);
