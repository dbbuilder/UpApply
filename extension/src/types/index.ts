/**
 * Shared TypeScript types used across content scripts, background, and sidebar.
 */

export interface ScreeningQuestion {
  question: string;
  inputSelector: string;
}

export interface JobData {
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
  fullDescription?: string;
}

export interface ScrapedProposal {
  proposalId: string | null;
  jobTitle: string | null;
  jobUrl: string | null;
  coverLetter: string | null;
  bidAmount: number | null;
  bidType: string | null;
  status: string | null;
  submittedAt: string | null;
}

export interface AttachmentInfo {
  url: string;
  filename: string;
  contentType: string;
}

export interface JobPostingData {
  fullDescription: string | null;
  attachments: AttachmentInfo[];
}
