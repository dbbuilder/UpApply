/**
 * Upwork DOM selectors for job data extraction.
 * These selectors are based on Upwork's current page structure.
 * They may need updates if Upwork changes their DOM.
 */

// Selector groups - we try multiple selectors in order
export const SELECTORS = {
  // Job details page & proposal page
  jobTitle: [
    // Proposal page selectors
    '[data-test="job-title-link"]',
    '.job-details-header h1',
    '.fe-proposal-job-title',
    'h2[data-test="JobTitle"]',
    // Job details page selectors
    'h4 a[href*="/jobs/"]',
    '[data-test="job-title"]',
    '.job-title-link',
    'header h1',
    'h1',
    'h2',
  ],

  jobDescription: [
    // Proposal page selectors
    '[data-test="job-description"]',
    '.job-details-description',
    '.fe-proposal-job-description',
    // Job details page selectors
    '[data-test="Description"]',
    '.break.mt-2',
    '[data-test="job-description-text"]',
    '.job-description',
    '.cfe-ui-job-description',
    // Generic fallback - look for large text blocks
    'section p',
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
    '[data-test="Skills"] .air3-token',
    '.skill-badge',
    '[data-test="attrs-skills"] .air3-token',
    '.up-skill-badge',
    '[data-cy="skill"]',
  ],

  // Experience level
  experienceLevel: [
    '[data-test="experience-level"]',
    '[data-cy="experience-level"]',
  ],

  // Project length
  projectLength: [
    '[data-test="duration"]',
    '[data-cy="duration"]',
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
