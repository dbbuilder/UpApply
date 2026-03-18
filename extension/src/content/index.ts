/**
 * Content script for extracting job data from Upwork pages.
 */

import {
  SELECTORS,
  extractText,
  extractTexts,
  querySelector,
  querySelectorAll,
} from './upwork-selectors';
import type { ScreeningQuestion, JobData, AttachmentInfo, JobPostingData } from '../types';
import { initDraftSaver } from './draft-saver';
import { logger } from '../lib/logger';
import { extractAllProposals, scrapeProposalPageText } from './scrapers/proposals';
import { scrapeAllContracts } from './scrapers/contracts';
import './scoring';

/**
 * Extract screening questions from the page.
 */
function extractScreeningQuestions(): ScreeningQuestion[] {
  const questions: ScreeningQuestion[] = [];

  // Find all question containers
  const questionContainers = document.querySelectorAll(
    '.fe-proposal-job-questions .form-group, .questions-area .form-group'
  );

  questionContainers.forEach((container, index) => {
    const label = container.querySelector('label, .label');
    const input = container.querySelector('textarea, input[type="text"]');

    if (label && input) {
      const questionText = label.textContent?.trim() || '';
      if (questionText) {
        // Create a unique selector for this input
        questions.push({
          question: questionText,
          inputSelector: input.id ? `#${input.id}` : `.fe-proposal-job-questions .form-group:nth-child(${index + 1}) textarea, .fe-proposal-job-questions .form-group:nth-child(${index + 1}) input`,
        });
      }
    }
  });

  return questions;
}

/**
 * Extract job data from the current page.
 */
function extractJobData(): JobData {
  const url = window.location.href;

  // Extract basic job info
  const title = extractText(SELECTORS.jobTitle);
  const description = extractText(SELECTORS.jobDescription);
  const skills = extractTexts(SELECTORS.skills);
  const experienceLevel = extractText(SELECTORS.experienceLevel);
  const projectLength = extractText(SELECTORS.projectLength);

  // Debug: if extraction failed, dump what we can find
  if (!title) {
    const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5')).slice(0, 10);
    logger.log('UpApply: Title not found. Page headings:', headings.map(h => ({
      tag: h.tagName,
      class: h.className.substring(0, 60),
      text: h.textContent?.trim().substring(0, 80),
      parent: h.parentElement?.className.substring(0, 60),
    })));
  }

  logger.log('UpApply: Extraction results:', {
    title: title?.substring(0, 60),
    descriptionLength: description?.length,
    skillCount: skills.length,
  });

  // Extract budget info
  const budgetAmount = extractText(SELECTORS.budgetAmount);
  let budgetType: string | null = null;

  // Determine budget type from content or selectors
  const hourlyElement = querySelector(SELECTORS.budgetType);
  if (hourlyElement?.textContent?.toLowerCase().includes('hourly')) {
    budgetType = 'hourly';
  } else if (budgetAmount?.toLowerCase().includes('/hr')) {
    budgetType = 'hourly';
  } else if (budgetAmount) {
    budgetType = 'fixed';
  }

  // Extract client info
  const clientRating = extractText(SELECTORS.clientRating);
  const clientLocation = extractText(SELECTORS.clientLocation);
  const clientSpent = extractText(SELECTORS.clientSpent);
  const clientHireRate = extractText(SELECTORS.clientHireRate);

  // Extract screening questions
  const screeningQuestions = extractScreeningQuestions();

  return {
    url,
    title,
    description,
    budgetType,
    budgetAmount,
    skills,
    experienceLevel,
    projectLength,
    screeningQuestions,
    clientInfo: {
      rating: clientRating,
      location: clientLocation,
      totalSpent: clientSpent,
      hireRate: clientHireRate,
    },
  };
}

/**
 * Check if we're on a job details page.
 */
function isJobPage(): boolean {
  return window.location.href.includes('/jobs/');
}

/**
 * Check if we're on the My Proposals page.
 */
function isMyProposalsPage(): boolean {
  const url = window.location.href;
  return url.includes('/freelancers/proposals') ||
         url.includes('/nx/find-work/proposals') ||
         url.includes('/nx/proposals') ||
         url.includes('/ab/proposals');
}

/**
 * Check if the current page has job card listings (saved jobs or search results).
 */
function isJobCardPage(): boolean {
  const url = window.location.href;
  return url.includes('/nx/search/jobs') || url.includes('/nx/find-work/');
}

interface ScrapedJobCard {
  upworkJobId: string;
  upworkUrl: string;
  title: string;
  description: string;
  jobType: string | null;
  experienceLevel: string | null;
  postedDateRaw: string | null;
  clientInfo: {
    paymentVerified: boolean;
    rating: string | null;
    totalSpent: string | null;
  };
}

/**
 * Extract job cards from a saved-jobs or search-results page.
 * Structure: article[data-test="JobTile"] with data-test-key=jobId
 */
function extractJobCards(): ScrapedJobCard[] {
  const cards: ScrapedJobCard[] = [];
  const articles = document.querySelectorAll('article[data-test="JobTile"]');

  articles.forEach((article) => {
    const titleLink = article.querySelector<HTMLAnchorElement>('a[data-test="job-tile-title-link"]');
    if (!titleLink) return;

    const title = titleLink.textContent?.trim() || '';
    const href = titleLink.getAttribute('href') || '';
    const fullUrl = href.startsWith('http') ? href : `https://www.upwork.com${href}`;

    // Extract job ID from URL: ~0(\d+) pattern
    const idMatch = fullUrl.match(/~0?(\d{15,})/);
    if (!idMatch) return;
    const upworkJobId = idMatch[1];

    const description = article.querySelector('[data-test="UpCLineClamp JobDescription"]')
      ?.textContent?.trim() || '';

    const jobTypeEl = article.querySelector('[data-test="job-type-label"]');
    const jobType = jobTypeEl?.textContent?.trim().toLowerCase().includes('fixed')
      ? 'fixed'
      : jobTypeEl?.textContent?.trim().toLowerCase().includes('hourly')
      ? 'hourly'
      : null;

    const expEl = article.querySelector('[data-test="experience-level"]');
    const experienceLevel = expEl?.textContent?.trim() || null;

    const dateEl = article.querySelector('[data-test="job-pubilshed-date"]');
    const postedDateRaw = dateEl?.textContent?.trim() || null;

    const paymentVerified = !!article.querySelector('[data-test="payment-verified"]');
    const ratingEl = article.querySelector('[data-test="total-feedback"]');
    const rating = ratingEl?.textContent?.trim() || null;
    const spentEl = article.querySelector('[data-test="total-spent"]');
    const totalSpent = spentEl?.textContent?.trim() || null;

    cards.push({
      upworkJobId,
      upworkUrl: fullUrl.split('?')[0], // strip query params
      title,
      description,
      jobType,
      experienceLevel,
      postedDateRaw,
      clientInfo: { paymentVerified, rating, totalSpent },
    });
  });

  return cards;
}

/**
 * Extract job cards across all pagination pages.
 */
async function extractAllJobCards(): Promise<ScrapedJobCard[]> {
  // Use same cross-instance lock as proposals
  const lockKey = '__upapplyJobCardScrapingPromise';
  const win = window as unknown as Record<string, unknown>;

  if (win[lockKey]) {
    logger.log('UpApply: Joining existing job card scrape');
    return win[lockKey] as Promise<ScrapedJobCard[]>;
  }

  const promise = (async () => {
    const all: ScrapedJobCard[] = [];

    // Read total pages from pagination attribute
    const paginationEl = document.querySelector('[data-ev-max_page_count]');
    const totalPages = paginationEl
      ? parseInt(paginationEl.getAttribute('data-ev-max_page_count') || '1', 10)
      : 1;
    const pagesToScrape = Math.min(totalPages, 50); // cap at 50 pages

    logger.log('UpApply: Job card scrape — total pages:', totalPages, 'scraping up to:', pagesToScrape);

    all.push(...extractJobCards());
    logger.log('UpApply: Page 1 —', all.length, 'job cards');

    for (let page = 2; page <= pagesToScrape; page++) {
      const nextBtn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
      if (!nextBtn || nextBtn.disabled) break;

      const firstCardId = document.querySelector('article[data-test="JobTile"]')?.getAttribute('data-test-key');
      nextBtn.click();

      // Wait for page to change
      await new Promise<void>((resolve) => {
        const start = Date.now();
        const poll = setInterval(() => {
          const newId = document.querySelector('article[data-test="JobTile"]')?.getAttribute('data-test-key');
          if (newId !== firstCardId || Date.now() - start > 3000) {
            clearInterval(poll);
            resolve();
          }
        }, 100);
      });

      // Wait for next button to re-enable
      await new Promise<void>((resolve) => {
        const start = Date.now();
        const poll = setInterval(() => {
          const btn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
          if (!btn?.disabled || Date.now() - start > 2000) {
            clearInterval(poll);
            resolve();
          }
        }, 100);
      });

      const pageCards = extractJobCards();
      all.push(...pageCards);
      logger.log('UpApply: Page', page, '—', pageCards.length, 'job cards (total:', all.length, ')');
    }

    return all;
  })();

  win[lockKey] = promise;
  try {
    return await promise;
  } finally {
    delete win[lockKey];
  }
}


/**
 * Infer content type from URL or filename.
 */
function inferContentType(url: string, filename: string): string {
  const ext = (url.match(/\.(\w+)(?:\?|$)/) || filename.match(/\.(\w+)$/) || [])[1]?.toLowerCase();
  const typeMap: Record<string, string> = {
    pdf: 'application/pdf',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    doc: 'application/msword',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    txt: 'text/plain',
  };
  return typeMap[ext] || 'application/octet-stream';
}

/**
 * Get the "View job posting" link URL from the current page.
 */
function getViewJobPostingLink(): string | null {
  const linkElement = querySelector(SELECTORS.viewJobPostingLink) as HTMLAnchorElement | null;
  if (linkElement?.href) {
    return linkElement.href;
  }
  return null;
}

/**
 * Extract job posting data from a job details page.
 * This is used when viewing the full job posting (not the /apply page).
 */
function extractJobPostingData(): JobPostingData {
  // Get full description
  const fullDescription = extractText(SELECTORS.jobPostingFullDescription);

  // Get attachments
  const attachmentElements = querySelectorAll(SELECTORS.jobPostingAttachments);
  const attachments: AttachmentInfo[] = [];
  const seenUrls = new Set<string>();

  for (const el of attachmentElements) {
    const link = el as HTMLAnchorElement;
    if (!link.href || seenUrls.has(link.href)) continue;

    // Skip non-attachment links
    if (!link.href.includes('attachment') &&
        !link.href.includes('/ab/') &&
        !link.href.match(/\.(pdf|docx?|png|jpe?g|gif|txt)(\?|$)/i)) {
      continue;
    }

    seenUrls.add(link.href);
    const filename = link.textContent?.trim() ||
                     link.getAttribute('download') ||
                     link.href.split('/').pop()?.split('?')[0] ||
                     'attachment';

    attachments.push({
      url: link.href,
      filename,
      contentType: inferContentType(link.href, filename),
    });
  }

  logger.log('UpApply: Extracted job posting data:', {
    descriptionLength: fullDescription?.length,
    attachmentCount: attachments.length,
  });

  return {
    fullDescription,
    attachments,
  };
}

/**
 * Fill the cover letter textarea with generated content.
 */
function fillCoverLetter(content: string): boolean {
  const textarea = querySelector(SELECTORS.coverLetterTextarea) as HTMLTextAreaElement | null;

  if (!textarea) {
    logger.warn('UpApply: Cover letter textarea not found');
    return false;
  }

  // Set value and trigger input event for React/Vue compatibility
  textarea.value = content;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  textarea.dispatchEvent(new Event('change', { bubbles: true }));

  // Focus the textarea
  textarea.focus();

  return true;
}

/**
 * Set the bid amount in the proposal form.
 */
function setBidAmount(amount: number): boolean {
  const input = querySelector(SELECTORS.bidAmountInput) as HTMLInputElement | null;

  if (!input) {
    logger.warn('UpApply: Bid amount input not found');
    return false;
  }

  input.value = amount.toString();
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));

  return true;
}

/**
 * Fill a screening question answer.
 */
function fillScreeningQuestion(selector: string, answer: string): boolean {
  try {
    const input = document.querySelector(selector) as HTMLTextAreaElement | HTMLInputElement | null;
    if (!input) {
      logger.warn('UpApply: Screening question input not found:', selector);
      return false;
    }

    input.value = answer;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  } catch (error) {
    console.error('UpApply: Error filling screening question:', error);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Milestone filling helpers
// ---------------------------------------------------------------------------

interface MilestoneData {
  description: string;
  days_from_start: number;
  amount: number;
}

/** Use the native setter to trigger Vue/React reactivity on an input. */
function _setNativeValue(input: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
  if (setter) {
    setter.call(input, value);
  } else {
    input.value = value;
  }
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
}

async function fillMilestones(milestones: MilestoneData[]): Promise<{ success: boolean; filled: number }> {
  const container = document.querySelector('[data-test="milestones"], .up-fe-milestones, [data-test="milestone-list"]');
  if (!container) return { success: false, filled: 0 };

  const addBtn = container.querySelector<HTMLElement>(
    '.milestone-add, [data-ev-label="milestone_add"], [data-test="add-milestone"], a[class*="add"], button[class*="add"]'
  ) || document.querySelector<HTMLElement>('[data-test="add-milestone"]');

  const initialCount = container.querySelectorAll('[data-test="milestone"], .up-fe-milestone, [data-test^="milestone-row"]').length;

  // Add milestone rows until we have enough
  for (let i = initialCount; i < milestones.length; i++) {
    addBtn?.click();
    await new Promise(r => setTimeout(r, 700)); // give React time to mount the new row
  }

  // Extra settle time after all additions before querying inputs
  if (milestones.length > initialCount) {
    await new Promise(r => setTimeout(r, 300));
  }

  const rows = container.querySelectorAll<HTMLElement>('[data-test="milestone"], .up-fe-milestone, [data-test^="milestone-row"]');
  let filled = 0;

  for (let i = 0; i < Math.min(milestones.length, rows.length); i++) {
    const ms = milestones[i];
    const row = rows[i];

    // Description — try data-test first, then common fallbacks for dynamically added rows
    const descInput = row.querySelector<HTMLInputElement | HTMLTextAreaElement>(
      '[data-test="milestone-description"], ' +
      'input[placeholder*="escription" i], ' +
      'textarea[placeholder*="escription" i], ' +
      'input[placeholder*="Describe" i], ' +
      'input[placeholder*="milestone" i], ' +
      'input[placeholder*="work to be" i], ' +
      'input[type="text"]:not([data-test="currency-input"])'
    );
    if (descInput) {
      _setNativeValue(descInput as HTMLInputElement, ms.description);
    }

    // Amount
    const amountInput = row.querySelector<HTMLInputElement>(
      '[data-test="milestone-amount"] [data-test="currency-input"], ' +
      '[data-test="currency-input"], ' +
      'input[type="number"], input[placeholder*="amount" i]'
    );
    if (amountInput) {
      _setNativeValue(amountInput, ms.amount.toFixed(2));
    }

    // Due date — compute absolute date from days_from_start
    const dateInput = row.querySelector<HTMLInputElement>(
      '[data-test="milestone-due-date"] [data-test="input"], ' +
      '[data-test="milestone-due-date"] input, ' +
      'input[placeholder*="date" i], input[placeholder*="MM/DD" i]'
    );
    if (dateInput && ms.days_from_start > 0) {
      const d = new Date();
      d.setDate(d.getDate() + ms.days_from_start);
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const yyyy = d.getFullYear();
      // Remove inputmode="none" so typing works, then set value
      dateInput.removeAttribute('inputmode');
      _setNativeValue(dateInput, `${mm}/${dd}/${yyyy}`);
    }

    filled++;
  }

  return { success: true, filled };
}



interface ScrapedSavedSearch {
  query: string;
  url_params: string;
  label: string;
}

/**
 * Extract saved searches from Upwork's find-work saved searches modal.
 *
 * Upwork saved searches use ?topic_id=XXXXX (not ?q=) in the link href.
 * The human-readable query is the link's text content (e.g. "azure").
 * We preserve the full URL params (including topic_id) so the search can
 * be replayed later. Also handles legacy ?q= search links as a fallback.
 */
function extractSavedSearches(): ScrapedSavedSearch[] {
  const results: ScrapedSavedSearch[] = [];
  const seen = new Set<string>();

  const links = document.querySelectorAll<HTMLAnchorElement>('a[href*="/nx/search/jobs"]');
  links.forEach((link) => {
    try {
      const url = new URL(link.href);
      const q = url.searchParams.get('q');
      const topicId = url.searchParams.get('topic_id');

      // Need at least one of q= or topic_id= to identify a search
      if (!q && !topicId) return;

      // Use link text as the human-readable label/query; fall back to q or topic_id
      const linkText = link.textContent?.trim();
      const query = linkText || q || topicId || '';
      if (!query) return;

      const normalized = query.toLowerCase();
      if (seen.has(normalized)) return;
      seen.add(normalized);

      // Preserve full URL params (topic_id + any filters) minus noise params
      const extra = new URLSearchParams(url.search);
      extra.delete('nbs');
      const urlParams = extra.toString();

      results.push({ query, url_params: urlParams, label: query });
    } catch {
      // Ignore malformed URLs
    }
  });

  return results;
}

/**
 * Handle messages from background script or sidebar.
 */
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  logger.log('UpApply: Received message', message.type, message);

  switch (message.type) {
    case 'PING':
      sendResponse({ pong: true });
      break;

    case 'EXTRACT_JOB_DATA':
      logger.log('UpApply: EXTRACT_JOB_DATA received, isJobPage:', isJobPage(), 'URL:', window.location.href);
      if (!isJobPage()) {
        logger.log('UpApply: Not a job page, returning error');
        sendResponse({ success: false, error: 'Not on a job page' });
        return true;
      }
      try {
        const jobData = extractJobData();
        logger.log('UpApply: Extraction complete, title:', jobData.title);
        if (!jobData.title) {
          // Send debug info back so it's visible in the background/sidebar console
          const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5')).slice(0, 8);
          const debug = headings.map(h => `<${h.tagName} class="${h.className.substring(0, 40)}"> ${h.textContent?.trim().substring(0, 60)}`);
          logger.log('UpApply: DEBUG headings:', debug);
          sendResponse({ success: true, data: jobData, debug });
        } else {
          sendResponse({ success: true, data: jobData });
        }
      } catch (err) {
        console.error('UpApply: Extraction error:', err);
        sendResponse({ success: false, error: String(err) });
      }
      return true;

    case 'FILL_COVER_LETTER':
      const filled = fillCoverLetter(message.content);
      sendResponse({ success: filled });
      break;

    case 'SET_BID_AMOUNT':
      const bidSet = setBidAmount(message.amount);
      sendResponse({ success: bidSet });
      break;

    case 'GET_PAGE_STATUS':
      sendResponse({
        isJobPage: isJobPage(),
        url: window.location.href,
      });
      break;

    case 'FILL_SCREENING_QUESTION':
      const questionFilled = fillScreeningQuestion(message.selector, message.answer);
      sendResponse({ success: questionFilled });
      break;

    case 'FILL_ALL_QUESTIONS': {
      // message.answers = [{index: number, answer: string}]
      const textareas = Array.from(
        document.querySelectorAll<HTMLTextAreaElement>(
          '.fe-proposal-job-questions .air3-textarea.inner-textarea, .questions-area .air3-textarea.inner-textarea'
        )
      );
      let filled = 0;
      for (const { index, answer } of message.answers as { index: number; answer: string }[]) {
        const ta = textareas[index];
        if (!ta || !answer) continue;
        ta.value = answer;
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        ta.dispatchEvent(new Event('change', { bubbles: true }));
        filled++;
      }
      sendResponse({ success: true, filled });
      break;
    }

    case 'FILL_MILESTONES': {
      (async () => {
        const result = await fillMilestones(message.milestones);
        try { sendResponse(result); } catch { /* channel closed */ }
      })();
      return true;
    }

    case 'SCRAPE_PROPOSALS': {
      if (!isMyProposalsPage()) {
        sendResponse({ success: false, error: 'Not on My Proposals page', url: window.location.href });
      } else {
        // Collect debug selector hits to send back to background console
        const debugHits: string[] = [];
        const debugSelectors = [
          '[data-test="proposal-list-item"]',
          '[data-test="proposals-list"] > *',
          '[data-test="proposal-row"]',
          '.proposals-list-item',
          '.up-card-section.up-card-list-section',
          '[class*="proposal" i]',
          '[class*="job-tile" i]',
          '[data-ev-label*="proposal" i]',
          'article',
          'li',
          'section',
        ];
        for (const sel of debugSelectors) {
          const count = document.querySelectorAll(sel).length;
          if (count > 0 && count < 200) debugHits.push(`"${sel}" × ${count}`);
        }
        (async () => {
          try {
            const proposals = await extractAllProposals();
            try { sendResponse({ success: true, data: proposals, url: window.location.href, debug: debugHits }); } catch { /* channel closed */ }
          } catch (err) {
            try { sendResponse({ success: false, error: String(err), debug: debugHits }); } catch { /* channel closed */ }
          }
        })();
        return true; // keep message channel open for async sendResponse
      }
      break;
    }

    case 'SCRAPE_PROPOSAL_DETAIL': {
      // Extract cover letter and metadata from a single /nx/proposals/{id} detail page.
      // Called by the background IMPORT_PROPOSALS deep-scraper for each detail URL.
      const coverLetter = scrapeProposalPageText();
      // Use a specific selector; avoid generic h3 which can match section headers like "Hiring activity"
      const titleEl = document.querySelector<HTMLElement>('[data-test="job-title"], h2.job-title, .job-title');
      const jobTitle = titleEl?.textContent?.trim() || null;
      sendResponse({ success: true, coverLetter, jobTitle });
      break;
    }

    case 'SCRAPE_JOB_CARDS': {
      if (!isJobCardPage()) {
        sendResponse({ success: false, error: 'Not on a job listings page', url: window.location.href });
      } else {
        (async () => {
          try {
            const cards = await extractAllJobCards();
            try { sendResponse({ success: true, data: cards, url: window.location.href }); } catch { /* channel closed */ }
          } catch (err) {
            try { sendResponse({ success: false, error: String(err) }); } catch { /* channel closed */ }
          }
        })();
        return true;
      }
      break;
    }

    case 'SCRAPE_SAVED_SEARCHES': {
      try {
        const results = extractSavedSearches();
        sendResponse({ success: true, data: results, url: window.location.href });
      } catch (err) {
        sendResponse({ success: false, error: String(err) });
      }
      break;
    }

    case 'SCRAPE_CONTRACTS': {
      (async () => {
        try {
          const data = await scrapeAllContracts();
          try { sendResponse({ success: true, data, url: window.location.href }); } catch { /* channel closed */ }
        } catch (err) {
          try { sendResponse({ success: false, error: String(err) }); } catch { /* channel closed */ }
        }
      })();
      return true; // async — keep message channel open
    }

    case 'GET_PAGE_TYPE':
      sendResponse({
        isJobPage: isJobPage(),
        isMyProposalsPage: isMyProposalsPage(),
        isJobCardPage: isJobCardPage(),
        url: window.location.href,
      });
      break;

    case 'GET_VIEW_POSTING_LINK':
      const viewLink = getViewJobPostingLink();
      sendResponse({ success: !!viewLink, url: viewLink });
      break;

    case 'EXTRACT_JOB_POSTING_DATA':
      try {
        const postingData = extractJobPostingData();
        sendResponse({ success: true, data: postingData });
      } catch (err) {
        console.error('UpApply: Job posting extraction error:', err);
        sendResponse({ success: false, error: String(err) });
      }
      break;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
  }

  // Do NOT return true here — async cases already return true from inside their
  // case block. Returning true unconditionally for sync cases (PING, EXTRACT_JOB_DATA,
  // etc.) causes "message channel closed" errors because Chrome waits for a second
  // async sendResponse that never comes.
});

/**
 * Guard against re-injection. The background script may re-inject
 * the content script, but we only want to initialize once per page.
 */
const INIT_FLAG = '__upapply_initialized__';

/**
 * Auto-fill cover letter from a pending Quick Apply initiated by the sidebar.
 * Checks chrome.storage for a pendingAutoFill entry matching this apply page.
 */
async function checkPendingAutoFill(): Promise<void> {
  if (!window.location.href.includes('/apply')) return;
  if (!chrome?.storage?.local) return;  // no-op if storage unavailable

  const result = await chrome.storage.local.get('pendingAutoFill');
  const pending = result.pendingAutoFill as {
    jobUrl: string;
    jobId: string;
    coverLetter: string;
    timestamp: number;
  } | undefined;

  if (!pending) return;

  // Expire after 5 minutes
  if (Date.now() - pending.timestamp > 5 * 60 * 1000) {
    await chrome.storage.local.remove('pendingAutoFill');
    return;
  }

  // Match by job slug (~XXXX) so URL format differences don't matter
  const urlSlug = window.location.href.match(/(~[a-zA-Z0-9]+)/)?.[1];
  const pendingSlug = pending.jobUrl?.match(/(~[a-zA-Z0-9]+)/)?.[1];
  if (!urlSlug || urlSlug !== pendingSlug) return;

  // Consume the pending fill immediately so it doesn't apply twice
  await chrome.storage.local.remove('pendingAutoFill');
  logger.log('UpApply: Pending auto-fill found for job slug', urlSlug);

  const tryFill = (): boolean => fillCoverLetter(pending.coverLetter);

  // Try immediately; if form not rendered yet, wait via MutationObserver
  if (!tryFill()) {
    const observer = new MutationObserver(() => {
      if (tryFill()) {
        observer.disconnect();
        logger.log('UpApply: Pending auto-fill applied via observer');
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Give up after 15 seconds
    setTimeout(() => observer.disconnect(), 15000);
  } else {
    logger.log('UpApply: Pending auto-fill applied immediately');
  }
}

/**
 * Initialize content script.
 */
function init() {
  // Prevent duplicate init from re-injection
  if ((window as unknown as Record<string, unknown>)[INIT_FLAG]) {
    logger.log('UpApply: Already initialized, skipping');
    return;
  }
  (window as unknown as Record<string, unknown>)[INIT_FLAG] = true;

  logger.log('UpApply: Content script loaded on', window.location.href);

  // Notify background script that we're ready
  chrome.runtime.sendMessage({
    type: 'CONTENT_SCRIPT_READY',
    url: window.location.href,
    isJobPage: isJobPage(),
  }).catch(() => { /* sidebar/background may not be listening */ });

  // Check for Quick Apply pending fill (fires when sidebar opens an apply page)
  checkPendingAutoFill().catch(() => {});

  // Initialize draft saver on proposal/apply pages
  initDraftSaver();

  // Watch for SPA navigation
  let lastUrl = window.location.href;
  const observer = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      logger.log('UpApply: URL changed to', lastUrl);

      // Re-extract job data on navigation — wait for React to finish rendering
      if (isJobPage()) {
        const sendExtraction = () => {
          const jobData = extractJobData();
          if (!jobData.title) return false; // not ready
          chrome.runtime.sendMessage({ type: 'JOB_DATA_EXTRACTED', data: jobData }).catch(() => {});
          return true;
        };
        setTimeout(() => {
          if (!sendExtraction()) {
            // Still empty — retry once more
            setTimeout(sendExtraction, 2000);
          }
        }, 3000);
      }

      // Re-initialize draft saver if navigated to apply page
      initDraftSaver();

      // Check for pending Quick Apply fill after SPA navigation
      checkPendingAutoFill().catch(() => {});
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
