/**
 * Upwork DOM selectors for job data extraction.
 * These selectors are based on Upwork's current page structure.
 * They may need updates if Upwork changes their DOM.
 */

// Selector groups - we try multiple selectors in order
export const SELECTORS = {
  // Job details page & proposal page
  jobTitle: [
    // Proposal/apply page - job title is h3 inside fe-job-details section
    '.fe-job-details .air3-card-section h3',
    '.fe-job-details section h3',
    '.fe-job-details h3',
    '.fe-job-details .content h3',
    // Job details page selectors
    '[data-test="job-title-link"]',
    'h4 a[href*="/jobs/"]',
    '[data-test="job-title"]',
    '.job-title-link',
    // Generic fallbacks (excluding "Submit a Proposal" h1)
    '.fe-job-details h2',
    'h2.h4',
  ],

  jobDescription: [
    // Proposal/apply page - description is in .description.text-body-sm
    '.fe-job-details .description.text-body-sm',
    '.fe-job-details .description span',
    '.fe-job-details .description',
    // Job details page selectors
    '[data-test="Description"]',
    '[data-test="job-description"]',
    '[data-test="job-description-text"]',
    '.job-description',
    '.cfe-ui-job-description',
    // Generic fallback
    '.description',
  ],

  // Budget information
  budgetAmount: [
    '[data-test="budget"]',
    '[data-test="is-fixed-price"]',
    '.cfe-ui-job-budget',
    '[data-cy="budget"]',
  ],

  budgetType: [
    '[data-test="is-hourly-job"]',
    '[data-test="is-fixed-price"]',
  ],

  // Skills
  skills: [
    // Proposal page skills
    '.fe-job-details .air3-token',
    '.fe-job-details [data-qa-skill-key] .air3-token',
    // Job details page skills
    '[data-test="Skills"] .air3-token',
    '.skill-badge',
    '[data-test="attrs-skills"] .air3-token',
    '.up-skill-badge',
    '[data-cy="skill"]',
  ],

  // Experience level
  experienceLevel: [
    // Proposal page - inside fe-ui-job-features
    '.fe-ui-job-features [data-cy="expertise"] + strong',
    '.fe-ui-job-features li:first-child strong',
    '[data-test="experience-level"]',
    '[data-cy="experience-level"]',
  ],

  // Project length
  projectLength: [
    // Proposal page
    '.fe-ui-job-features [data-test="hourly-duration"] strong',
    '[data-test="duration"]',
    '[data-cy="duration"]',
  ],

  // Screening questions (0 to several per job)
  screeningQuestions: [
    '.fe-proposal-job-questions .form-group',
    '.questions-area .form-group',
    '[data-test="screening-question"]',
  ],

  screeningQuestionLabel: [
    'label',
    '.label',
  ],

  screeningQuestionInput: [
    'textarea',
    'input[type="text"]',
    '.air3-textarea',
  ],

  // Client information
  clientRating: [
    '[data-test*="rating"]',
    '.air3-rating',
    '.up-rating',
  ],

  clientLocation: [
    '[data-test="LocalTime"]',
    '[data-test="client-location"]',
    '.cfe-ui-job-details-client-location',
  ],

  clientSpent: [
    '[data-test="total-spent"]',
    ':has-text("total spent")',
  ],

  clientHireRate: [
    '[data-test="hire-rate"]',
  ],

  // Proposal page
  coverLetterTextarea: [
    'textarea[aria-labelledby="cover_letter_label"]',
    '#cover_letter',
    '[data-test="cover-letter-input"]',
    'textarea[name="cover_letter"]',
  ],

  bidAmountInput: [
    '[data-test="hourly-rate"]',
    '[data-test="bid-amount"]',
    'input[name="hourly_rate"]',
    'input[name="amount"]',
  ],

  submitButton: [
    'button:has-text("Submit Proposal")',
    '[data-test="submit-proposal"]',
    'button[type="submit"]',
  ],

  // My Proposals page selectors (for scraping proposal history)
  proposalListItem: [
    '[data-test="proposal-list-item"]',
    '.proposals-list-item',
    '.my-proposals-list article',
    '.up-card-section.up-card-list-section',
  ],

  proposalJobTitle: [
    '[data-test="proposal-job-title"]',
    '.proposal-job-title',
    'h4 a',
    '.job-title-link',
  ],

  proposalCoverLetter: [
    '[data-test="proposal-cover-letter"]',
    '.proposal-cover-letter',
    '.cover-letter-text',
  ],

  proposalStatus: [
    '[data-test="proposal-status"]',
    '.proposal-status',
    '.status-badge',
  ],

  proposalBidAmount: [
    '[data-test="proposal-bid"]',
    '.proposal-bid-amount',
  ],

  proposalSubmittedDate: [
    '[data-test="proposal-date"]',
    '.proposal-submitted-date',
    'time',
  ],

  proposalJobUrl: [
    'a[href*="/jobs/"]',
    '[data-test="job-link"]',
  ],

  // View job posting link (on /apply pages)
  viewJobPostingLink: [
    '.fe-job-details a[href*="/jobs/~"]',
    'a[href*="/jobs/~"][class*="up-n-link"]',
    'a.air3-link[href*="/jobs/~"]',
    '[data-test="view-posting-link"]',
    'a[href*="/freelance-jobs/"]',
  ],

  // Full job posting page selectors (different from /apply page)
  jobPostingFullDescription: [
    '[data-test="Description"]',
    '[data-test="job-description"]',
    '.cfe-ui-job-description-text',
    '.job-description .text-body',
    '.description.text-body-sm',
    'section.job-description',
  ],

  // Job posting attachments
  jobPostingAttachments: [
    '[data-test="attachments"] a',
    '.attachments-section a[href]',
    '.job-attachments a',
    'a[href*="/attachment/"]',
    'a[href*="/ab/attachments/"]',
    '.air3-card-section a[href*="upwork.com"][download]',
    '.job-details a[href*=".pdf"]',
    '.job-details a[href*=".doc"]',
    '.job-details a[href*=".png"]',
    '.job-details a[href*=".jpg"]',
  ],
} as const;

/**
 * Try multiple selectors until one matches
 */
export function querySelector(selectors: readonly string[]): Element | null {
  for (const selector of selectors) {
    try {
      // Handle :has-text pseudo-selector manually
      if (selector.includes(':has-text')) {
        const match = selector.match(/:has-text\("([^"]+)"\)/);
        if (match) {
          const text = match[1];
          const baseSelector = selector.replace(/:has-text\("[^"]+"\)/, '');
          const elements = document.querySelectorAll(baseSelector || '*');
          for (const el of elements) {
            if (el.textContent?.toLowerCase().includes(text.toLowerCase())) {
              return el;
            }
          }
        }
        continue;
      }

      const element = document.querySelector(selector);
      if (element) return element;
    } catch {
      // Invalid selector, try next
      continue;
    }
  }
  return null;
}

/**
 * Try multiple selectors and return all matching elements
 */
export function querySelectorAll(selectors: readonly string[]): Element[] {
  const results: Element[] = [];
  const seen = new Set<Element>();

  for (const selector of selectors) {
    try {
      const elements = document.querySelectorAll(selector);
      for (const el of elements) {
        if (!seen.has(el)) {
          seen.add(el);
          results.push(el);
        }
      }
    } catch {
      continue;
    }
  }

  return results;
}

/**
 * Extract text content from the first matching selector
 */
export function extractText(selectors: readonly string[]): string | null {
  const element = querySelector(selectors);
  return element?.textContent?.trim() || null;
}

/**
 * Extract texts from all matching elements
 */
export function extractTexts(selectors: readonly string[]): string[] {
  const elements = querySelectorAll(selectors);
  return elements
    .map(el => el.textContent?.trim())
    .filter((text): text is string => !!text);
}
