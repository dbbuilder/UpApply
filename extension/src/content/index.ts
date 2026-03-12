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
import type { ScreeningQuestion, JobData, ScrapedProposal, AttachmentInfo, JobPostingData } from '../types';
import { initDraftSaver } from './draft-saver';
import { detectNotifChips } from '../lib/notif-chips';

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
    console.log('UpApply: Title not found. Page headings:', headings.map(h => ({
      tag: h.tagName,
      class: h.className.substring(0, 60),
      text: h.textContent?.trim().substring(0, 80),
      parent: h.parentElement?.className.substring(0, 60),
    })));
  }

  console.log('UpApply: Extraction results:', {
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
    console.log('UpApply: Joining existing job card scrape');
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

    console.log('UpApply: Job card scrape — total pages:', totalPages, 'scraping up to:', pagesToScrape);

    all.push(...extractJobCards());
    console.log('UpApply: Page 1 —', all.length, 'job cards');

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
      console.log('UpApply: Page', page, '—', pageCards.length, 'job cards (total:', all.length, ')');
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
 * Extract proposals from the My Proposals page.
 */
function extractProposals(): ScrapedProposal[] {
  const proposals: ScrapedProposal[] = [];
  const seen = new Set<string>();

  // Strategy: anchor off proposal list row links.
  // On /nx/proposals/ the links use data-ev-label="jpn_list_details_link" and
  // href="/nx/proposals/{numericId}". Status comes from the <tr>'s data-ev-sublocation.
  // Fallback: any <a href*="/nx/proposals/"> that links to a numeric proposal ID.
  const proposalLinks = Array.from(
    document.querySelectorAll<HTMLAnchorElement>(
      'a[data-ev-label="jpn_list_details_link"], a[href*="/nx/proposals/"]:not([href$="/nx/proposals/"])'
    )
  );
  console.log('UpApply: Found', proposalLinks.length, 'proposal links');

  for (const link of proposalLinks) {
    const href = link.getAttribute('href') || '';
    const proposalUrl = new URL(href, window.location.origin).href;
    // Extract numeric proposal ID from /nx/proposals/{numericId}
    const proposalIdMatch = proposalUrl.match(/\/nx\/proposals\/(\d+)/);
    const proposalId = proposalIdMatch?.[1] || null;
    if (!proposalId || seen.has(proposalId)) continue;
    seen.add(proposalId);

    const jobTitle = link.textContent?.trim() || link.getAttribute('aria-label')?.replace(/ Boosted$/, '').trim() || null;
    if (!jobTitle) continue;

    // The <tr> contains data-ev-sublocation indicating which section this is in
    const row = link.closest('tr');
    const sublocation = row?.getAttribute('data-ev-sublocation') || '';
    let status = 'submitted';
    if (sublocation === 'active_candidacies') status = 'responded';
    else if (sublocation === 'interviews') status = 'interviewed';

    // Date is in <td data-cy="time-slot">
    let submittedAt: string | null = null;
    const timeSlot = row?.querySelector('td[data-cy="time-slot"]');
    if (timeSlot) {
      // Text like "Initiated\nMar 3, 2026" or "Received\nFeb 28, 2026"
      const rawText = timeSlot.textContent?.trim() || '';
      const dateMatch = rawText.match(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,\s+\d{4}/);
      if (dateMatch) submittedAt = dateMatch[0];
    }

    proposals.push({
      proposalId,
      jobTitle,
      jobUrl: proposalUrl, // best available — proposal detail URL
      coverLetter: null,   // not visible on list page
      bidAmount: null,     // not visible on list page
      bidType: null,
      status,
      submittedAt,
    });
  }

  console.log('UpApply: Extracted', proposals.length, 'proposals');
  return proposals;
}

// window-level key for the shared scraping promise (shared across all
// instances of this content script injected into the same tab).
const SCRAPE_KEY = '__upapplyScrapingPromise';

/**
 * Wait for the next-page button to become enabled (not disabled).
 * The button is briefly disabled during page transitions.
 */
function waitForNextButton(timeoutMs = 2000): Promise<HTMLButtonElement | null> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      const btn = document.querySelector<HTMLButtonElement>('button[data-test="next-page"]');
      if (!btn) { resolve(null); return; }
      if (!btn.disabled) { resolve(btn); return; }
      if (Date.now() >= deadline) { resolve(null); return; }
      setTimeout(check, 100);
    };
    setTimeout(check, 100);
  });
}

/**
 * Wait for new proposal links to appear after a page navigation click.
 * Resolves when the first proposal link's href changes or a timeout occurs.
 */
function waitForProposalPageChange(previousFirstId: string | null, timeoutMs = 2500): Promise<void> {
  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs;
    const check = () => {
      const first = document.querySelector<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]');
      const firstId = first?.getAttribute('href') || null;
      if (firstId && firstId !== previousFirstId) {
        resolve();
      } else if (Date.now() >= deadline) {
        resolve(); // timeout — extract whatever's there
      } else {
        setTimeout(check, 150);
      }
    };
    setTimeout(check, 150);
  });
}

/**
 * Extract proposals across all pagination pages by clicking "next page"
 * until the last page is reached. Uses a lock to prevent concurrent runs
 * when multiple content script instances are active.
 */
async function extractAllProposals(): Promise<ScrapedProposal[]> {
  const win = window as unknown as Record<string, unknown>;

  // If another instance already started scraping, share its result
  if (win[SCRAPE_KEY]) {
    console.log('UpApply: Joining existing scrape in progress');
    return win[SCRAPE_KEY] as Promise<ScrapedProposal[]>;
  }

  // Become the leader — store the promise so other instances join it
  const scrapePromise = (async (): Promise<ScrapedProposal[]> => {
    const paginationDiv = document.querySelector('[data-ev-max_page_count]');
    const totalPages = paginationDiv
      ? parseInt(paginationDiv.getAttribute('data-ev-max_page_count') || '1', 10)
      : 1;

    console.log('UpApply: Proposals pagination — total pages:', totalPages);

    const all: ScrapedProposal[] = [];
    const seenIds = new Set<string>();

    const addPage = (page: ScrapedProposal[]) => {
      for (const p of page) {
        if (p.proposalId && !seenIds.has(p.proposalId)) {
          seenIds.add(p.proposalId);
          all.push(p);
        }
      }
    };

    // Page 1 is already loaded
    addPage(extractProposals());

    for (let page = 2; page <= totalPages; page++) {
      const firstLink = document.querySelector<HTMLAnchorElement>('a[data-ev-label="jpn_list_details_link"]');
      const previousFirstHref = firstLink?.getAttribute('href') || null;

      // Wait for next button to be enabled (it's briefly disabled during transitions)
      const nextBtn = await waitForNextButton();
      if (!nextBtn) {
        console.log('UpApply: No enabled next button found at page', page - 1, '— stopping');
        break;
      }

      console.log('UpApply: Clicking to page', page, 'of', totalPages);
      nextBtn.click();
      await waitForProposalPageChange(previousFirstHref);

      addPage(extractProposals());
    }

    console.log('UpApply: Total proposals across all pages:', all.length);
    return all;
  })();

  win[SCRAPE_KEY] = scrapePromise;
  try {
    return await scrapePromise;
  } finally {
    delete win[SCRAPE_KEY];
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

  console.log('UpApply: Extracted job posting data:', {
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
    console.warn('UpApply: Cover letter textarea not found');
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
    console.warn('UpApply: Bid amount input not found');
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
      console.warn('UpApply: Screening question input not found:', selector);
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

// ---------------------------------------------------------------------------
// Notification page job scorer
// ---------------------------------------------------------------------------

const _scoredNotifUrls = new Set<string>();

/** Strip query params and trailing slashes so the same job with different
 *  tracking params (?source=notification, ?source=job-alert, etc.) counts
 *  as the same URL. */
function _normalizeJobUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.origin + u.pathname.replace(/\/+$/, '');
  } catch {
    return url;
  }
}

// ---------------------------------------------------------------------------
// Star rating — combines score + budget into 1–5 ★ for quick visual triage
// ---------------------------------------------------------------------------

function _parseBudgetFromChips(chips: string[]): { amount: number; type: 'hourly' | 'fixed' } | null {
  const chip = chips.find(c => c.startsWith('$'));
  if (!chip) return null;
  // Use top-of-range if it's a range like "$50-$100/hr"
  const top = chip.replace(/^\$[\d,]+(?:\.\d+)?\s*[-–]\s*/, ''); // strip lower bound
  const isHourly = /\/h(r|our)?/.test(chip);
  const num = parseFloat(top.replace(/[^0-9.]/g, ''));
  if (!num || isNaN(num)) return null;
  return { amount: num, type: isHourly ? 'hourly' : 'fixed' };
}

function _computeStars(score: number, chips: string[]): number {
  // Base stars from AI score
  let stars: number;
  if (score >= 85) stars = 5;
  else if (score >= 70) stars = 4;
  else if (score >= 52) stars = 3;
  else if (score >= 35) stars = 2;
  else stars = 1;

  // Budget modifier: ±1 based on rate/amount
  const budget = _parseBudgetFromChips(chips);
  if (budget) {
    const { amount, type } = budget;
    const isHigh = type === 'hourly' ? amount >= 100 : amount >= 8000;
    const isLow  = type === 'hourly' ? amount < 25   : amount < 400;
    if (isHigh) stars = Math.min(5, stars + 1);
    else if (isLow) stars = Math.max(1, stars - 1);
  }

  return stars;
}

function _starsDisplay(stars: number): string {
  return '★'.repeat(stars) + '☆'.repeat(5 - stars);
}

function _starsColors(stars: number): { bg: string; color: string } {
  if (stars >= 5) return { bg: '#b45309', color: '#fff' }; // amber/gold
  if (stars >= 4) return { bg: '#15803d', color: '#fff' }; // green
  if (stars >= 3) return { bg: '#ca8a04', color: '#fff' }; // yellow
  if (stars >= 2) return { bg: '#9a3412', color: '#fff' }; // orange
  return { bg: '#6b7280', color: '#fff' };                  // gray
}

// Job data stored at score time so action panel can save/generate without re-fetching
interface _JobRecord {
  title: string;
  description: string;
  skills: string[];
  savedJobId?: string;  // set after first successful POST /api/v1/jobs
}
const _jobDataStore = new Map<string, _JobRecord>();

/** Trim the chip list based on star tier — fewer stars = less visual noise. */
function _filterChipsByStars(chips: string[], stars: number): string[] {
  const budgetChip = chips.find(c => c.startsWith('$'));
  const keywords   = chips.filter(c => !c.startsWith('$'));

  if (stars >= 4) return chips;                                      // all chips
  if (stars === 3) return [...keywords.slice(0, 3), ...(budgetChip ? [budgetChip] : [])]; // 3 keywords + budget
  if (stars === 2) return budgetChip ? [budgetChip] : [];            // budget only
  return [];                                                          // 1★: none
}

function _injectNotifBadge(row: Element, jobUrl: string): HTMLElement {
  const badge = document.createElement('span');
  badge.dataset.upapplyJob = _normalizeJobUrl(jobUrl);
  badge.style.cssText =
    'display:inline-flex;align-items:center;justify-content:center;' +
    'min-width:62px;height:22px;border-radius:11px;' +
    'font-size:13px;font-weight:700;color:#9ca3af;' +
    'background:#f3f4f6;border:1px solid #e5e7eb;' +
    'padding:0 6px;margin-left:8px;vertical-align:middle;' +
    'cursor:default;font-family:-apple-system,sans-serif;white-space:nowrap;letter-spacing:1px;';
  badge.textContent = '…';
  badge.title = 'UpApply: scoring…';
  const link = row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
  if (link) link.after(badge);
  return badge;
}

interface _NotifQueueItem {
  badge: HTMLElement;
  row: Element;
  jobUrl: string;
  title: string;
}
const _notifQueue: _NotifQueueItem[] = [];
let _notifProcessing = false;
let _notifTotal = 0;   // total jobs queued in this scoring run
let _notifDone  = 0;   // jobs completed (success or failure)
let _contractImportBtnInjected = false;
let _workroomProposalBtnInjected = false;

/** Reset all scoring state — called on SPA navigation so stale flags never block a fresh run. */
function _resetNotifState(): void {
  _notifQueue.length = 0;
  _notifProcessing = false;
  _notifTotal = 0;
  _notifDone = 0;
  _scoredNotifUrls.clear();
  _scoreButtonInjected = false;
  _savedBtnInjected = false;
  _contractImportBtnInjected = false;
  _workroomProposalBtnInjected = false;
  _clearAuthTokenCache();
  _closeActivePanel();
  _jobDataStore.clear();
  _hudVisibleRows.clear();
  if (_hud) _hud.style.display = 'none';
  document.getElementById('ua-score-btn')?.remove();
  document.getElementById('ua-saved-score-btn')?.remove();
  document.getElementById('ua-contract-import-btn')?.remove();
  document.getElementById('ua-workroom-proposal-btn')?.remove();
  document.getElementById('ua-notif-progress')?.remove();
}

// Chip colour map — specific keywords get accent colours, budget is neutral
const _CHIP_COLORS: Record<string, { bg: string; color: string }> = {
  'MVP':       { bg: '#7c3aed', color: '#fff' },  // purple
  'SaaS':      { bg: '#0891b2', color: '#fff' },  // teal
  'Azure':     { bg: '#0078d4', color: '#fff' },  // Microsoft blue
  'SQL':       { bg: '#b45309', color: '#fff' },  // amber
  'Role':      { bg: '#374151', color: '#fff' },  // dark gray
  'AI':        { bg: '#4f46e5', color: '#fff' },  // indigo
  'Python':    { bg: '#2563eb', color: '#fff' },  // blue
  'React':     { bg: '#0e7490', color: '#fff' },  // cyan-700
  'API':       { bg: '#475569', color: '#fff' },  // slate
  'CTO':       { bg: '#6d28d9', color: '#fff' },  // violet (high-value)
  'Cloud':     { bg: '#0284c7', color: '#fff' },  // sky
  'Auto':      { bg: '#c2410c', color: '#fff' },  // orange (automation)
  'Urgent':    { bg: '#dc2626', color: '#fff' },  // red
  'Long-term': { bg: '#059669', color: '#fff' },  // emerald
};

const _CHIP_BASE_CSS =
  'display:inline-flex;align-items:center;justify-content:center;' +
  'height:20px;border-radius:10px;' +
  'font-size:11px;font-weight:600;' +
  'vertical-align:middle;' +
  'font-family:-apple-system,sans-serif;white-space:nowrap;letter-spacing:0.01em;';

function _makeChipEl(label: string): HTMLElement {
  const chip = document.createElement('span');
  const colors = _CHIP_COLORS[label] ?? { bg: '#166534', color: '#fff' };
  chip.style.cssText =
    _CHIP_BASE_CSS +
    `background:${colors.bg};color:${colors.color};padding:0 7px;margin-left:5px;`;
  chip.textContent = label;
  chip.dataset.upapplyChip = label;
  return chip;
}

function _injectChips(row: Element, chips: string[]): void {
  chips.forEach((label) => {
    const chip = _makeChipEl(label);
    const all = [...row.querySelectorAll<HTMLElement>('[data-upapply-job],[data-upapply-chip]')];
    const last = all[all.length - 1];
    if (last) last.after(chip);
  });
}

// ---------------------------------------------------------------------------
// Action panel — score details + Apply Queue + Cover Letter
// ---------------------------------------------------------------------------

let _activePanel: { el: HTMLElement; timer: ReturnType<typeof setTimeout> | null } | null = null;

function _closeActivePanel(): void {
  if (_activePanel) {
    _activePanel.el.remove();
    if (_activePanel.timer) clearTimeout(_activePanel.timer);
    _activePanel = null;
  }
}
function _cancelClosePanel(): void {
  if (_activePanel?.timer) { clearTimeout(_activePanel.timer); _activePanel.timer = null; }
}
function _scheduleClosePanel(): void {
  if (!_activePanel) return;
  _activePanel.timer = setTimeout(_closeActivePanel, 350);
}

/** Save the job to the API (idempotent — caches savedJobId). */
async function _ensureJobSaved(jobUrl: string, token: string, apiBase: string, fallbackTitle = ''): Promise<string | null> {
  const rec = _jobDataStore.get(jobUrl);
  if (rec?.savedJobId) return rec.savedJobId;

  // Lazy-fetch description if not already cached from scoring
  let title = rec?.title || fallbackTitle || 'Job';
  let description = rec?.description || '';
  let skills = rec?.skills || [];
  if (!description) {
    const d = await _fetchJobData(jobUrl);
    description = d.description || title;
    skills = d.skills || [];
  }

  const resp = await fetch(`${apiBase}/api/v1/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    body: JSON.stringify({
      upwork_url: jobUrl,
      title,
      description,
      skills_required: skills.length ? skills : undefined,
    }),
    signal: AbortSignal.timeout(25_000),
  });
  if (!resp.ok) return null;
  const job = await resp.json() as { id: string };
  if (rec) rec.savedJobId = job.id;
  else _jobDataStore.set(jobUrl, { title, description, skills, savedJobId: job.id });
  return job.id;
}

function _makeActionRow(
  text: string,
  accentColor: string,
  onClick: (cb: HTMLElement, lbl: HTMLElement) => Promise<void>,
): HTMLElement {
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;user-select:none;';

  const cb = document.createElement('span');
  cb.style.cssText =
    `display:inline-flex;align-items:center;justify-content:center;` +
    `width:16px;height:16px;border-radius:4px;border:1.5px solid ${accentColor};` +
    `font-size:10px;flex-shrink:0;transition:background 0.15s;`;

  const lbl = document.createElement('span');
  lbl.textContent = text;
  lbl.style.cssText = `font-size:11px;color:${accentColor};font-weight:600;white-space:nowrap;`;

  row.appendChild(cb);
  row.appendChild(lbl);

  let running = false;
  row.addEventListener('click', (e) => {
    e.stopPropagation();
    if (running || cb.dataset.done === '1') return;
    running = true;
    cb.style.background = '#f3f4f6';
    onClick(cb, lbl).finally(() => { running = false; });
  });
  return row;
}

async function _queueJobAction(jobUrl: string, title: string, cb: HTMLElement, lbl: HTMLElement): Promise<void> {
  const token = await _getAuthToken();
  if (!token) { lbl.textContent = '× Not logged in'; lbl.style.color = '#ef4444'; return; }
  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
  try {
    lbl.textContent = '⟳ Saving job…';
    const jobId = await _ensureJobSaved(jobUrl, token, apiBase, title);
    if (!jobId) throw new Error('save failed');
    lbl.textContent = '⟳ Queuing…';
    const r = await fetch(`${apiBase}/api/v1/applications`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ job_id: jobId }),
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) throw new Error(`${r.status}`);
    cb.textContent = '✓'; cb.dataset.done = '1';
    cb.style.cssText += 'background:#16a34a;border-color:#16a34a;color:#fff;';
    lbl.textContent = 'Apply Queue'; lbl.style.color = '#16a34a';
  } catch {
    lbl.textContent = '× Failed'; lbl.style.color = '#ef4444';
  }
}

async function _coverLetterAction(jobUrl: string, title: string, cb: HTMLElement, lbl: HTMLElement): Promise<void> {
  const token = await _getAuthToken();
  if (!token) { lbl.textContent = '× Not logged in'; lbl.style.color = '#ef4444'; return; }
  const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
  try {
    lbl.textContent = '⟳ Saving job…';
    const jobId = await _ensureJobSaved(jobUrl, token, apiBase, title);
    lbl.textContent = '⟳ Generating…';
    const body = jobId
      ? { job_id: jobId, include_call_offer: true }
      : { job_data: { upwork_url: jobUrl, title, description: _jobDataStore.get(jobUrl)?.description || title }, include_call_offer: true };
    const r = await fetch(`${apiBase}/api/v1/jobs/cover-letters/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60_000),
    });
    if (!r.ok) throw new Error(`${r.status}`);
    cb.textContent = '✓'; cb.dataset.done = '1';
    cb.style.cssText += 'background:#1d4ed8;border-color:#1d4ed8;color:#fff;';
    lbl.textContent = '+ Cover Letter'; lbl.style.color = '#1d4ed8';
  } catch {
    lbl.textContent = '× Failed'; lbl.style.color = '#ef4444';
  }
}

function _showActionPanel(badge: HTMLElement, jobUrl: string, title: string, stars: number, score: number, chips: string[], reason: string): void {
  _closeActivePanel();

  const rect = badge.getBoundingClientRect();
  const panelLeft = Math.min(rect.left, window.innerWidth - 330 - 8);
  const openAbove = (window.innerHeight - rect.bottom) < 160;

  const panel = document.createElement('div');
  panel.style.cssText = [
    'position:fixed',
    openAbove ? `bottom:${window.innerHeight - rect.top + 6}px` : `top:${rect.bottom + 6}px`,
    `left:${panelLeft}px`,
    'z-index:2147483647',
    'background:#fff',
    'border:1px solid #e5e7eb',
    'border-radius:10px',
    'box-shadow:0 4px 18px rgba(0,0,0,0.16)',
    'padding:10px 12px',
    'min-width:240px',
    'max-width:320px',
    'font-family:system-ui,-apple-system,sans-serif',
  ].join(';');

  // Row 1: stars pill + score + budget
  const { bg, color } = _starsColors(stars);
  const budgetChip = chips.find(c => c.startsWith('$'));
  const topRow = document.createElement('div');
  topRow.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px;';

  const starPill = document.createElement('span');
  starPill.textContent = _starsDisplay(stars);
  starPill.style.cssText = `background:${bg};color:${color};font-size:12px;font-weight:700;border-radius:6px;padding:2px 8px;letter-spacing:1px;flex-shrink:0;`;
  topRow.appendChild(starPill);

  const scoreEl = document.createElement('span');
  scoreEl.textContent = `${score}/100`;
  scoreEl.style.cssText = 'font-size:12px;font-weight:700;color:#374151;';
  topRow.appendChild(scoreEl);

  if (budgetChip) {
    const budgetEl = document.createElement('span');
    budgetEl.textContent = budgetChip;
    budgetEl.style.cssText = 'font-size:11px;font-weight:600;color:#059669;background:#d1fae5;padding:1px 6px;border-radius:4px;margin-left:auto;white-space:nowrap;';
    topRow.appendChild(budgetEl);
  }
  panel.appendChild(topRow);

  // Bonus chips (those hidden by star tier)
  const visibleSet = new Set(_filterChipsByStars(chips, stars));
  const bonusChips = chips.filter(c => !visibleSet.has(c) && !c.startsWith('$'));
  if (bonusChips.length) {
    const chipRow = document.createElement('div');
    chipRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px;';
    bonusChips.forEach(label => {
      const c = _makeChipEl(label);
      c.style.marginLeft = '0';
      chipRow.appendChild(c);
    });
    panel.appendChild(chipRow);
  }

  // Reason text
  if (reason) {
    const reasonEl = document.createElement('div');
    reasonEl.textContent = reason.length > 110 ? reason.slice(0, 110) + '…' : reason;
    reasonEl.style.cssText = 'font-size:11px;color:#6b7280;line-height:1.4;margin-bottom:8px;';
    panel.appendChild(reasonEl);
  }

  // Divider
  const divider = document.createElement('div');
  divider.style.cssText = 'border-top:1px solid #f3f4f6;margin-bottom:7px;';
  panel.appendChild(divider);

  // Action rows
  panel.appendChild(_makeActionRow('+ Apply Queue', '#16a34a', (c, l) => _queueJobAction(jobUrl, title, c, l)));
  const clRow = _makeActionRow('+ Cover Letter', '#1d4ed8', (c, l) => _coverLetterAction(jobUrl, title, c, l));
  clRow.style.marginTop = '2px';
  panel.appendChild(clRow);

  document.body.appendChild(panel);
  _activePanel = { el: panel, timer: null };

  panel.addEventListener('mouseenter', _cancelClosePanel);
  panel.addEventListener('mouseleave', _scheduleClosePanel);

  // Close on outside click
  const closeOnClick = (e: MouseEvent) => {
    if (!panel.contains(e.target as Node) && e.target !== badge) {
      _closeActivePanel();
      document.removeEventListener('click', closeOnClick, true);
    }
  };
  setTimeout(() => document.addEventListener('click', closeOnClick, true), 0);
}

function _attachBadgePanel(badge: HTMLElement, jobUrl: string, title: string, stars: number, score: number, chips: string[], reason: string): void {
  badge.style.cursor = 'pointer';
  badge.addEventListener('mouseenter', () => {
    _cancelClosePanel();
    _showActionPanel(badge, jobUrl, title, stars, score, chips, reason);
  });
  badge.addEventListener('mouseleave', _scheduleClosePanel);
  badge.addEventListener('click', (e) => {
    e.stopPropagation();
    if (_activePanel) { _closeActivePanel(); }
    else { _showActionPanel(badge, jobUrl, title, stars, score, chips, reason); }
  });
}

// ---------------------------------------------------------------------------
// Progress bar injected near the notification bell
// ---------------------------------------------------------------------------

function _getOrCreateProgressBar(): HTMLElement {
  let bar = document.getElementById('ua-notif-progress');
  if (bar) return bar;

  bar = document.createElement('div');
  bar.id = 'ua-notif-progress';
  bar.style.cssText =
    'position:fixed;bottom:80px;right:16px;z-index:2147483647;' +
    'background:#1d4ed8;color:#fff;' +
    'font-size:11px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'padding:5px 10px;border-radius:20px;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);' +
    'display:flex;align-items:center;gap:6px;white-space:nowrap;' +
    'transition:opacity 0.3s;';

  const spinner = document.createElement('span');
  spinner.id = 'ua-notif-spinner';
  spinner.style.cssText =
    'width:10px;height:10px;border-radius:50%;border:2px solid rgba(255,255,255,0.4);' +
    'border-top-color:#fff;animation:ua-spin 0.7s linear infinite;';
  bar.appendChild(spinner);

  const label = document.createElement('span');
  label.id = 'ua-notif-label';
  bar.appendChild(label);

  // Keyframes (inject once)
  if (!document.getElementById('ua-notif-styles')) {
    const style = document.createElement('style');
    style.id = 'ua-notif-styles';
    style.textContent = '@keyframes ua-spin{to{transform:rotate(360deg)}}';
    document.head.appendChild(style);
  }

  document.body.appendChild(bar);
  return bar;
}

function _updateProgressBar(done: number, total: number): void {
  const bar = _getOrCreateProgressBar();
  const label = bar.querySelector<HTMLElement>('#ua-notif-label')!;
  label.textContent = `UpApply scoring ${done}/${total}…`;
  bar.style.opacity = '1';
}

function _hideProgressBar(): void {
  const bar = document.getElementById('ua-notif-progress');
  if (!bar) return;
  bar.style.opacity = '0';
  setTimeout(() => bar.remove(), 400);
}

// ---------------------------------------------------------------------------
// Fetch job data via Upwork's internal GraphQL API
// Content script runs on upwork.com so cookies are sent automatically.
// This avoids opening background tabs and bypasses bot-detection entirely.
// ---------------------------------------------------------------------------

function _getUpworkCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|;\\s*)${encodeURIComponent(name)}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

interface JobFetchResult {
  description: string;
  pageText: string;
  budgetAmount: string | null;
  budgetType: 'hourly' | 'fixed' | null;
  skills: string[];
  clientCountry: string | null;
}

/**
 * Primary path: call Upwork's internal GraphQL API with the job UID.
 * Uses the session cookies already present in the browser.
 */
async function _fetchJobViaGraphQL(jobUid: string): Promise<JobFetchResult | null> {
  // Upwork stores the OAuth bearer token in a JS-readable cookie
  const authToken = _getUpworkCookie('oauth2_global_js_token');
  // CSRF double-submit cookie (Angular/Vue SPA pattern)
  const xsrfToken = _getUpworkCookie('XSRF-TOKEN') || _getUpworkCookie('x-odesk-csrf-token');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  if (xsrfToken) headers['X-XSRF-TOKEN'] = xsrfToken;

  // Minimal query — only the fields we need
  // Note: Upwork changed the argument from jobUid → jobPostingId (same ~UID value)
  const query = `query jobPosting($jobPostingId:String!){
    jobPosting(jobPostingId:$jobPostingId){
      id title description contractorTier jobType
      hourlyBudgetMin hourlyBudgetMax
      amount{ amount currencyCode }
      skills{ prettyName }
      client{ location{ country } }
    }
  }`;

  const resp = await fetch('/api/graphql/v1', {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify({ operationName: 'jobPosting', query, variables: { jobPostingId: jobUid } }),
    signal: AbortSignal.timeout(8000),
  });

  console.log('[UpApply] GraphQL status:', resp.status, 'for', jobUid);
  if (!resp.ok) return null;

  const json = await resp.json() as { data?: { jobPosting?: Record<string, unknown> }; errors?: unknown[] };
  console.log('[UpApply] GraphQL response:', JSON.stringify(json).slice(0, 400));

  const job = json?.data?.jobPosting;
  if (!job) return null;

  // Budget
  let budgetAmount: string | null = null;
  let budgetType: 'hourly' | 'fixed' | null = null;
  const hMin = job.hourlyBudgetMin as number | null;
  const hMax = job.hourlyBudgetMax as number | null;
  const fixedAmt = (job.amount as Record<string, unknown> | null)?.amount as number | null;

  if (hMin != null || hMax != null) {
    budgetType = 'hourly';
    const min = hMin != null ? `$${Math.round(hMin)}` : null;
    const max = hMax != null ? `$${Math.round(hMax)}` : null;
    budgetAmount = [min, max].filter(Boolean).join('-');
  } else if (fixedAmt != null) {
    budgetType = 'fixed';
    budgetAmount = `$${Math.round(fixedAmt).toLocaleString()}`;
  }

  const description = (job.description as string) || '';
  const skillsRaw = (job.skills as Array<{ prettyName?: string }> | null) || [];
  const skills = skillsRaw.map(s => s.prettyName || '').filter(Boolean);
  const clientData = job.client as { location?: { country?: string } } | null;
  const clientCountry = clientData?.location?.country || null;
  return { description, pageText: description, budgetAmount, budgetType, skills, clientCountry };
}

// _fetchJobViaHTML removed: Upwork is CSR so the HTML shell is nearly empty,
// and DOMParser.parseFromString on a ~1MB page runs synchronously on the
// main thread. With 3 concurrent workers this caused "Page Unresponsive".
// GraphQL is the only fetch path; title is used as fallback if it returns empty.

/** Fetch job data via GraphQL only. HTML fallback removed — Upwork is CSR so
 *  the HTML shell is nearly empty and DOMParser on a ~1MB page runs synchronously
 *  on the main thread, causing "Page Unresponsive" when multiple workers hit it. */
async function _fetchJobData(jobUrl: string): Promise<JobFetchResult> {
  const uidMatch = jobUrl.match(/(~[0-9a-f]+)/i);
  if (uidMatch) {
    const result = await _fetchJobViaGraphQL(uidMatch[1]).catch(() => null);
    if (result && result.description.length > 0) {
      console.log('[UpApply] GraphQL success:', { descLen: result.description.length, budget: result.budgetAmount });
      return result;
    }
  }
  return { description: '', pageText: '', budgetAmount: null, budgetType: null, skills: [], clientCountry: null };
}

// ---------------------------------------------------------------------------
// Auth token — read once from chrome.storage.local, cached in memory.
// Content script calls the API directly; no service worker round trip needed.
// ---------------------------------------------------------------------------

let _contentAuthToken: string | null | undefined = undefined;

async function _getAuthToken(): Promise<string | null> {
  if (_contentAuthToken !== undefined) return _contentAuthToken;
  if (chrome?.storage?.local) {
    const stored = await chrome.storage.local.get('authToken');
    _contentAuthToken = (stored['authToken'] as string) || null;
  } else {
    // chrome.storage unavailable in this module context — ask background SW
    try {
      const resp = await chrome.runtime.sendMessage({ type: 'GET_AUTH_TOKEN' }) as { token: string | null };
      _contentAuthToken = resp?.token || null;
    } catch {
      _contentAuthToken = null;
    }
  }
  return _contentAuthToken;
}

/** Called on SPA navigation to force re-read of token on next scoring run. */
function _clearAuthTokenCache(): void {
  _contentAuthToken = undefined;
}

/** Score a single item and update its badge. Never throws. */
async function _scoreOneNotif(item: _NotifQueueItem): Promise<void> {
  const uid = item.jobUrl.match(/(~[0-9a-f]+)/i)?.[1] ?? item.jobUrl.slice(-12);
  console.log(`[UpApply] score START  ${uid} "${item.title.slice(0, 40)}"`);
  try {
    // 1. Persistent cache check
    const CACHE_KEY = `sc_v8_${item.jobUrl}`;
    const CACHE_TTL = 24 * 60 * 60 * 1000;
    const storageAvailable = !!(chrome?.storage?.local);
    if (storageAvailable) {
      const cacheStore = await chrome.storage.local.get(CACHE_KEY);
      const cached = cacheStore[CACHE_KEY] as { score: number; chips: string[]; reason?: string; ts: number } | undefined;
      if (cached && Date.now() - cached.ts < CACHE_TTL) {
        console.log(`[UpApply] score CACHED ${uid} score=${cached.score}`);
        _applyBadgeResult(item, cached.score, cached.chips, true, cached.reason);
        return;
      }
    } else {
      // Fallback: ask background for cached value
      try {
        const resp = await chrome.runtime.sendMessage({ type: 'GET_NOTIF_CACHE', key: CACHE_KEY }) as { value: { score: number; chips: string[]; reason?: string; ts: number } | null };
        const cached = resp?.value;
        if (cached && Date.now() - cached.ts < CACHE_TTL) {
          console.log(`[UpApply] score CACHED(SW) ${uid} score=${cached.score}`);
          _applyBadgeResult(item, cached.score, cached.chips, true, cached.reason);
          return;
        }
      } catch { /* skip cache on error */ }
    }

    // 2. Auth token (read once per scoring session, cached in memory)
    const token = await _getAuthToken();
    if (!token) {
      item.badge.textContent = '?';
      item.badge.style.background = '#6b7280';
      item.badge.title = 'UpApply: not logged in';
      return;
    }

    // 3. Fetch job description via Upwork GraphQL (content script context, 8s timeout)
    console.log(`[UpApply] score FETCH  ${uid}`);
    const jobData = await _fetchJobData(item.jobUrl);
    const description = jobData.description || item.title;
    console.log(`[UpApply] score FETCH  ${uid} done — descLen=${description.length} budget=${jobData.budgetAmount} source=${jobData.description ? 'graphql' : 'title-fallback'}`);

    // 4. Score via API directly (no SW message channel — eliminates zombie channel accumulation)
    console.log(`[UpApply] score SCORE  ${uid}`);
    const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL']
      || 'https://upapply-api.onrender.com';
    const apiResp = await fetch(`${apiBase}/api/v1/jobs/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        title: item.title || 'Job',
        description: description || item.title,
        skills_required: jobData.skills.length > 0 ? jobData.skills : undefined,
        client_info: jobData.clientCountry ? { location: jobData.clientCountry } : undefined,
      }),
      signal: AbortSignal.timeout(25_000),
    });

    if (!apiResp.ok) throw new Error(`API ${apiResp.status}`);
    const data = await apiResp.json() as { match_score: number; reason?: string };
    console.log(`[UpApply] score SCORE  ${uid} done — score=${data.match_score}`);

    // 5. Compute chips and cache result
    const chips = detectNotifChips(item.title, description, jobData.budgetAmount, jobData.budgetType);
    const cacheValue = { score: data.match_score, chips, reason: data.reason, ts: Date.now() };
    if (storageAvailable) {
      await chrome.storage.local.set({ [CACHE_KEY]: cacheValue });
    } else {
      chrome.runtime.sendMessage({ type: 'SET_NOTIF_CACHE', key: CACHE_KEY, value: cacheValue }).catch(() => {});
    }

    // Store full job data so the action panel can save/generate without re-fetching
    _jobDataStore.set(item.jobUrl, {
      title: item.title,
      description,
      skills: jobData.skills,
    });

    _applyBadgeResult(item, data.match_score, chips, false, data.reason);
    console.log(`[UpApply] score DONE   ${uid}`);
  } catch (err) {
    console.error(`[UpApply] score ERROR  ${uid}`, err);
    item.badge.textContent = '?';
    item.badge.style.background = '#6b7280';
    item.badge.title = 'UpApply: scoring error';
  }
}

function _applyBadgeResult(item: _NotifQueueItem, score: number, chips: string[], fromCache: boolean, reason?: string): void {
  const rounded = Math.round(score);
  const stars = _computeStars(rounded, chips);
  const { bg, color } = _starsColors(stars);
  item.badge.style.background = bg;
  item.badge.style.color = color;
  item.badge.style.border = 'none';
  item.badge.textContent = _starsDisplay(stars);
  item.badge.title = `UpApply: ${stars}★  (score ${rounded}/100)${fromCache ? ' · cached' : ''} — click for details`;
  const visibleChips = _filterChipsByStars(chips, stars);
  if (visibleChips.length) _injectChips(item.row, visibleChips);
  _attachBadgePanel(item.badge, item.jobUrl, item.title, stars, rounded, chips, reason ?? '');

  // Inject scoring reason as a blue line below the job title link
  if (reason) {
    const existingReason = item.row.querySelector('[data-upapply-reason]');
    if (!existingReason) {
      const link = item.row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
      if (link) {
        const reasonEl = document.createElement('span');
        reasonEl.setAttribute('data-upapply-reason', '1');
        reasonEl.textContent = reason;
        reasonEl.style.cssText = 'display:block;color:#3b82f6;font-size:11px;line-height:1.4;margin-top:3px;font-weight:normal;';
        link.insertAdjacentElement('afterend', reasonEl);
      }
    }
  }

  // Persist to scoredJobsCache for the sidebar's Find view
  if (chrome?.storage?.local) {
    chrome.storage.local.get('scoredJobsCache', (data) => {
      const cache: Record<string, { url: string; title: string; score: number; chips: string[]; scored_at: string }> =
        data.scoredJobsCache || {};
      cache[item.jobUrl] = {
        url: item.jobUrl,
        title: item.title || '',
        score: rounded,
        chips,
        scored_at: new Date().toISOString(),
      };
      // Cap at 500 entries — evict oldest by scored_at
      const entries = Object.values(cache).sort((a, b) => b.scored_at.localeCompare(a.scored_at));
      const capped: typeof cache = {};
      entries.slice(0, 500).forEach(e => { capped[e.url] = e; });
      chrome.storage.local.set({ scoredJobsCache: capped });
    });
  }

  // Fire-and-forget write to API job-reviews for persistence across sessions
  _getAuthToken().then(token => {
    if (!token) return;
    const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
    // Parse budget from chips
    const budgetChip = chips.find(c => c.startsWith('$'));
    const budgetType = budgetChip?.includes('/hr') ? 'hourly' : budgetChip ? 'fixed' : undefined;
    fetch(`${apiBase}/api/v1/job-reviews`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        upwork_job_url: item.jobUrl,
        job_title: item.title || '',
        ai_score: score,
        chips,
        budget_amount: budgetChip || null,
        budget_type: budgetType || null,
        scored_at: new Date().toISOString(),
      }),
      signal: AbortSignal.timeout(10_000),
    }).catch(() => {}); // silent — never block badge display
  }).catch(() => {});

  // Register this row with the scroll HUD so its score shows while it's visible
  _observeRowForHud(item.row);
}

// ---------------------------------------------------------------------------
// Floating scroll HUD — shows score of the topmost visible scored job
// ---------------------------------------------------------------------------
let _hud: HTMLElement | null = null;
const _hudVisibleRows = new Set<Element>();
let _hudObserver: IntersectionObserver | null = null;

function _refreshHud(): void { /* HUD removed — inline star badges are sufficient */ }

function _observeRowForHud(row: Element): void {
  if (!_hudObserver) {
    _hudObserver = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) _hudVisibleRows.add(e.target);
        else _hudVisibleRows.delete(e.target);
      }
      _refreshHud();
    }, { threshold: 0.15 });
  }
  _hudObserver.observe(row);
}

async function _processNotifQueue(): Promise<void> {
  if (_notifProcessing) {
    console.warn('[UpApply] _processNotifQueue called while already processing — skipped');
    return;
  }
  _notifProcessing = true;
  _notifDone = 0;
  _updateProgressBar(0, _notifTotal);

  const items = _notifQueue.splice(0);
  console.log(`[UpApply] queue START total=${items.length}`);

  try {
    for (const item of items) {
      // Yield to the browser event loop before each item.
      // One item at a time prevents concurrent DOM updates from stacking
      // Vue re-renders, which is what causes "Page Unresponsive".
      await new Promise<void>(resolve => setTimeout(resolve, 50));
      // Hard 35s ceiling per item (8s GraphQL + 25s API + 2s buffer).
      // MUST clearTimeout when scoring wins — otherwise the stale callback
      // fires later and overwrites a successfully-set score badge with '?'.
      let hardTimeoutId: ReturnType<typeof setTimeout>;
      await Promise.race([
        _scoreOneNotif(item).finally(() => clearTimeout(hardTimeoutId)),
        new Promise<void>(resolve => {
          hardTimeoutId = setTimeout(() => {
            console.warn(`[UpApply] item hard timeout: ${item.jobUrl}`);
            item.badge.textContent = '?';
            item.badge.style.background = '#6b7280';
            item.badge.title = 'UpApply: timed out';
            resolve();
          }, 35_000);
        }),
      ]);
      _notifDone++;
      _updateProgressBar(_notifDone, _notifTotal);
      console.log(`[UpApply] progress ${_notifDone}/${_notifTotal}`);
    }
  } finally {
    console.log(`[UpApply] queue FINISHED done=${_notifDone}/${_notifTotal}`);
    _notifProcessing = false;
    _hideProgressBar();
  }
}

function _processNotificationRows(): void {
  // Works for both the bell dropdown AND the full /ab/notifications/ page.
  // Both use .notification-row elements containing a[href*="/jobs/~"] links.
  document.querySelectorAll<Element>('.notification-row').forEach((row) => {
    // Skip rows that already have a badge (prevents double-injection when
    // MutationObserver fires on our own DOM changes)
    if (row.querySelector('[data-upapply-job]')) return;
    const link = row.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
    if (!link) return;
    const jobUrl = _normalizeJobUrl(link.href);
    if (_scoredNotifUrls.has(jobUrl)) return;
    _scoredNotifUrls.add(jobUrl);
    const title = link.textContent?.trim() || '';
    const badge = _injectNotifBadge(row, jobUrl);
    _notifQueue.push({ badge, row, jobUrl, title });
    _notifTotal++;
  });
  _processNotifQueue();
}

function _processSavedJobCards(): void {
  document.querySelectorAll<Element>('article[data-test="JobTile"]').forEach((article) => {
    if (article.querySelector('[data-upapply-job]')) return;
    const link = article.querySelector<HTMLAnchorElement>('a[href*="/jobs/~"]');
    if (!link) return;
    const jobUrl = _normalizeJobUrl(link.href);
    if (_scoredNotifUrls.has(jobUrl)) return;
    _scoredNotifUrls.add(jobUrl);
    const title = link.textContent?.trim() || '';
    const badge = _injectNotifBadge(article, jobUrl);
    _notifQueue.push({ badge, row: article, jobUrl, title });
    _notifTotal++;
  });
  _processNotifQueue();
}

// ---------------------------------------------------------------------------
// Score buttons — fixed overlays injected into document.body, never into
// Vue-managed component trees (which breaks Upwork's event handlers).
// ---------------------------------------------------------------------------

let _scoreButtonInjected = false;
let _savedBtnInjected = false;

const _BTN_STYLE =
  'position:fixed;bottom:80px;right:16px;z-index:2147483647;' +
  'display:flex;align-items:center;gap:6px;' +
  'padding:6px 14px;border-radius:20px;cursor:pointer;' +
  'background:#1d4ed8;color:#fff;' +
  'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
  'box-shadow:0 2px 8px rgba(0,0,0,0.25);white-space:nowrap;' +
  'user-select:none;transition:background 0.15s;';

function _makeScoreBtn(id: string, label: string, onClick: () => void): void {
  document.getElementById(id)?.remove();
  const btn = document.createElement('div');
  btn.id = id;
  btn.style.cssText = _BTN_STYLE;
  btn.textContent = label;
  btn.title = label;
  btn.addEventListener('mouseenter', () => { btn.style.background = '#1e40af'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#1d4ed8'; });
  btn.addEventListener('click', () => { btn.remove(); onClick(); });
  document.body.appendChild(btn);
}

function _injectScoreButton(): void {
  if (_scoreButtonInjected) return;
  _scoreButtonInjected = true;
  document.getElementById('ua-score-btn')?.remove();

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.style.cssText =
    'background:#1d4ed8;color:#fff;border:none;cursor:pointer;' +
    'padding:5px 12px;border-radius:20px;font-size:11px;font-weight:600;' +
    'font-family:-apple-system,sans-serif;white-space:nowrap;' +
    'display:flex;align-items:center;gap:4px;' +
    'box-shadow:0 1px 4px rgba(0,0,0,0.2);transition:background 0.15s;';
  btn.textContent = '⚡ Score';
  btn.title = 'Score all notifications';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#1e40af'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#1d4ed8'; });
  btn.addEventListener('click', () => {
    document.getElementById('ua-score-btn')?.remove();
    _scoreButtonInjected = false;
    _processNotificationRows();
  });

  // Prefer inserting as a nav sibling right after the bell <li>
  const bellLi = document.querySelector('[data-cy="notifications-menu"]');
  if (bellLi?.parentNode) {
    const li = document.createElement('li');
    li.id = 'ua-score-btn';
    li.style.cssText = 'list-style:none;display:flex;align-items:center;padding:0 4px;';
    li.appendChild(btn);
    bellLi.parentNode.insertBefore(li, bellLi.nextSibling);
  } else {
    // Fallback: fixed just below the nav bar on the right
    btn.id = 'ua-score-btn';
    btn.style.cssText += 'position:fixed;top:64px;right:16px;z-index:2147483647;';
    document.body.appendChild(btn);
  }
}

function _injectSavedJobsButton(): void {
  if (_savedBtnInjected) return;
  _savedBtnInjected = true;
  _makeScoreBtn('ua-saved-score-btn', '⚡ Score saved jobs', () => {
    _savedBtnInjected = false;
    _processSavedJobCards();
  });
}

// MutationObserver covers three cases:
//   1. Bell dropdown: inject score button (user-triggered scoring)
//   2. Full notifications page (/ab/notifications/): auto-score rows
//   3. Saved jobs page (/nx/search/jobs/saved/): auto-score tiles
let _lastObservedPath = window.location.pathname;
let _observerDebounce: ReturnType<typeof setTimeout> | undefined;

function _handleMutations(): void {
  // Upwork is a SPA — detect pushState navigation and reset stale scoring state
  // so _notifProcessing=true from a previous page never blocks a fresh run.
  const currentPath = window.location.pathname;
  if (currentPath !== _lastObservedPath) {
    _lastObservedPath = currentPath;
    _resetNotifState();
  }

  const isNotifPage = currentPath.includes('/notifications');
  const isSavedPage = currentPath.includes('/nx/search/jobs');
  const hasRows     = !!document.querySelector('.notification-row a[href*="/jobs/~"]');
  const hasTiles    = !!document.querySelector('article[data-test="JobTile"]');

  // Notification button: only show on the dedicated notifications page, never on
  // other pages just because the bell dropdown happens to be open.
  if (isNotifPage && hasRows && !_notifProcessing) {
    _injectScoreButton();
  } else if (_scoreButtonInjected && !_notifProcessing) {
    document.getElementById('ua-score-btn')?.remove();
    _scoreButtonInjected = false;
  }

  // Saved jobs button: show when tiles are present — never auto-score
  if (isSavedPage && hasTiles && !_notifProcessing) {
    _injectSavedJobsButton();
  } else if (_savedBtnInjected && !_notifProcessing) {
    document.getElementById('ua-saved-score-btn')?.remove();
    _savedBtnInjected = false;
  }

  // Contract import button: show on /nx/wm/freelancer/contracts (actual Upwork URL)
  // Also accepts the legacy /nx/contracts path in case Upwork changes it back.
  const isContractsPage = currentPath.includes('/wm/freelancer/contracts')
    || currentPath === '/nx/contracts';
  const hasContracts = !!document.querySelector('section[data-test^="contract-"]');
  if (isContractsPage && hasContracts && !_contractImportBtnInjected) {
    _injectContractImportButton();
  } else if (_contractImportBtnInjected && (!isContractsPage || !hasContracts)) {
    document.getElementById('ua-contract-import-btn')?.remove();
    _contractImportBtnInjected = false;
  }

  // Proposal save button: show on /nx/proposals/{id} pages when cover letter text is found.
  // User navigates to a hired proposal and clicks to save it as a winning example.
  const isProposalDetailPage = /\/nx\/proposals\/\d+/.test(currentPath)
    || /\/ab\/proposals\/\d+/.test(currentPath);
  if (isProposalDetailPage && !_workroomProposalBtnInjected) {
    const proposalText = _scrapeProposalPageText();
    if (proposalText) {
      _injectProposalSaveButton(proposalText);
    }
  } else if (_workroomProposalBtnInjected && !isProposalDetailPage) {
    document.getElementById('ua-workroom-proposal-btn')?.remove();
    _workroomProposalBtnInjected = false;
  }
}

new MutationObserver(() => {
  // Debounce: Upwork's SPA triggers bursts of mutations during navigation.
  // Running 5 querySelector calls on every mutation causes main-thread jank
  // that blocks header clicks. 200ms keeps responsiveness while still
  // catching dropdown open/close reliably.
  clearTimeout(_observerDebounce);
  _observerDebounce = setTimeout(_handleMutations, 200);
}).observe(document.body, { childList: true, subtree: true });

// No auto-scoring on any page — all scoring is user-initiated via buttons

// ---------------------------------------------------------------------------
// Contract history importer — /nx/contracts page
// ---------------------------------------------------------------------------

interface ScrapedContract {
  contract_id: string;
  title: string;
  contract_type: string;
  rate: string | null;
  status: string;
  client_name: string | null;
  date_range: string | null;
}

function _scrapeContracts(): ScrapedContract[] {
  const results: ScrapedContract[] = [];
  document.querySelectorAll<HTMLElement>('section[data-test^="contract-"]').forEach(section => {
    const testVal = section.getAttribute('data-test') || '';
    const idMatch = testVal.match(/^contract-(\d+)$/);
    if (!idMatch) return;
    const id = idMatch[1];

    const titleEl = section.querySelector<HTMLElement>(`[data-test="contract-${id}-title"]`);
    const title = titleEl?.getAttribute('title') || titleEl?.textContent?.trim() || '';
    if (!title) return;

    const hourlyEl = section.querySelector(`[data-test="contract-${id}-hourly-terms"]`);
    const fixedEl  = section.querySelector(`[data-test="contract-${id}-fixed-price-terms"]`);
    const contract_type = hourlyEl ? 'hourly' : fixedEl ? 'fixed' : 'unknown';
    const rate = (hourlyEl || fixedEl)?.textContent?.trim() || null;

    const status = section.querySelector(`[data-test="contract-${id}-active-info"]`) ? 'active'
      : section.querySelector(`[data-test="contract-${id}-paused-info"]`) ? 'paused'
      : 'ended';

    const clientEl = section.querySelector<HTMLElement>(`[data-test="contract-${id}-contract-party-info-section"] p`);
    const client_name = clientEl?.textContent?.replace(/^Hired by\s+/i, '').trim() || null;

    const datesEl = section.querySelector(`[data-test="contract-${id}-dates"]`);
    const date_range = datesEl?.textContent?.trim() || null;

    results.push({ contract_id: id, title, contract_type, rate, status, client_name, date_range });
  });
  return results;
}

/**
 * Click through all pagination pages and collect every contract.
 * Uses data-ev-max_page_count to know how many pages exist, then
 * clicks [data-test="next-page"] and waits for Vue to re-render each page.
 */
async function _scrapeAllContracts(): Promise<ScrapedContract[]> {
  const all: ScrapedContract[] = [];

  // Detect total pages from pagination buttons (most reliable — data-ev-max_page_count
  // is not present on the live contracts page).
  // "Current page 1 of N" sr-only text is the most explicit signal; fall back to
  // counting the numbered page buttons.
  let maxPages = 1;
  const srOnly = document.querySelector('.air3-pagination-nr-btn.is-active .sr-only');
  const srMatch = srOnly?.textContent?.match(/of\s+(\d+)/i);
  if (srMatch) {
    maxPages = parseInt(srMatch[1], 10);
  } else {
    const pageItems = document.querySelectorAll('[data-test="pagination-item"]');
    if (pageItems.length > 0) maxPages = pageItems.length;
  }

  const reportPage = (page: number) => {
    if (chrome?.storage?.local) {
      chrome.storage.local.set({ contractImportProgress: { stage: 'scraping', page, total: maxPages } });
    }
  };

  reportPage(1);
  all.push(..._scrapeContracts());

  for (let page = 2; page <= maxPages; page++) {
    const nextBtn = document.querySelector<HTMLButtonElement>('[data-test="next-page"]');
    if (!nextBtn || nextBtn.disabled || nextBtn.classList.contains('is-disabled')) break;

    nextBtn.click();

    // Step 1: wait for the active page button to show the new page number
    await new Promise<void>(resolve => {
      const deadline = Date.now() + 8000;
      const check = () => {
        const active = document.querySelector('.air3-pagination-nr-btn.is-active span[aria-hidden="true"]');
        if (active?.textContent?.trim() === String(page)) resolve();
        else if (Date.now() > deadline) resolve();
        else setTimeout(check, 200);
      };
      setTimeout(check, 300);
    });

    // Step 2: wait for Upwork to remove old sections and render new ones.
    // Sections briefly drop to 0 between pages — poll until they reappear.
    await new Promise<void>(resolve => {
      const deadline = Date.now() + 6000;
      let seenEmpty = false;
      const check = () => {
        const count = document.querySelectorAll('section[data-test^="contract-"]').length;
        if (count === 0) seenEmpty = true;
        if ((seenEmpty && count > 0) || Date.now() > deadline) resolve();
        else setTimeout(check, 100);
      };
      setTimeout(check, 100);
    });

    reportPage(page);
    all.push(..._scrapeContracts());
  }

  return all;
}

function _injectContractImportButton(): void {
  if (_contractImportBtnInjected) return;
  _contractImportBtnInjected = true;
  document.getElementById('ua-contract-import-btn')?.remove();

  const btn = document.createElement('div');
  btn.id = 'ua-contract-import-btn';
  btn.style.cssText =
    'position:fixed;bottom:140px;right:16px;z-index:2147483647;' +
    'display:flex;align-items:center;gap:6px;' +
    'padding:6px 14px;border-radius:20px;cursor:pointer;' +
    'background:#1d4ed8;color:#fff;' +
    'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);white-space:nowrap;' +
    'user-select:none;transition:background 0.15s;';
  btn.textContent = '📥 Import wins';
  btn.title = 'Import contract history as won jobs';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#1e40af'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#1d4ed8'; });
  btn.addEventListener('click', () => {
    _contractImportBtnInjected = false;
    btn.textContent = 'Importing…';
    btn.style.cursor = 'default';
    chrome.runtime.sendMessage({ type: 'IMPORT_CONTRACTS' }, (resp: { success: boolean; imported?: number; updated?: number; error?: string } | undefined) => {
      if (resp?.success) {
        btn.textContent = `✓ ${(resp.imported ?? 0) + (resp.updated ?? 0)} wins imported`;
      } else {
        btn.textContent = `✗ ${resp?.error || 'Import failed'}`;
      }
      setTimeout(() => { btn.remove(); }, 3000);
    });
  });
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------
// Proposal page scraper — /nx/proposals/{id}
// Captures the winning cover letter/proposal text and saves it as a Proposal
// record (was_hired=true) so cover letter generation can learn from it.
//
// DOM structure (confirmed from proposaldetails.html):
//   div[data-cy="cover-letter-section"]        ← container card
//     section.air3-card-section
//       p.break.text-pre-line                  ← the proposal text
//       [data-test="questions-answers"]         ← Q&A responses (append if present)
// ---------------------------------------------------------------------------

/** Extract cover letter text from an Upwork proposal detail page. */
function _scrapeProposalPageText(): string | null {
  // Primary: confirmed selector from DOM analysis
  const section = document.querySelector('[data-cy="cover-letter-section"]');
  if (section) {
    // Collect the cover letter paragraph(s)
    const parts: string[] = [];
    section.querySelectorAll('p.break.text-pre-line').forEach(p => {
      const t = p.textContent?.trim();
      if (t) parts.push(t);
    });
    // Also grab Q&A answers if present — they add context for scoring calibration
    section.querySelectorAll('[data-test="questions-answers"] span.air3-truncation').forEach(span => {
      const t = span.textContent?.trim();
      if (t) parts.push(t);
    });
    if (parts.length && parts.join('').length > 50) return parts.join('\n\n');
  }

  // Fallback: .cover-letter-section (older Upwork markup)
  const fallback = document.querySelector('.cover-letter-section p.break, .cover-letter p');
  if (fallback) {
    const t = fallback.textContent?.trim();
    if (t && t.length > 50) return t;
  }

  return null;
}

function _injectProposalSaveButton(proposalText: string): void {
  if (_workroomProposalBtnInjected) return;
  _workroomProposalBtnInjected = true;
  document.getElementById('ua-workroom-proposal-btn')?.remove();

  const btn = document.createElement('div');
  btn.id = 'ua-workroom-proposal-btn';
  btn.style.cssText =
    'position:fixed;bottom:140px;right:16px;z-index:2147483647;' +
    'display:flex;align-items:center;gap:6px;' +
    'padding:6px 14px;border-radius:20px;cursor:pointer;' +
    'background:#16a34a;color:#fff;' +
    'font-size:12px;font-weight:600;font-family:-apple-system,sans-serif;' +
    'box-shadow:0 2px 8px rgba(0,0,0,0.25);white-space:nowrap;' +
    'user-select:none;transition:background 0.15s;';
  btn.textContent = '💾 Save as winning proposal';
  btn.title = 'Mark this as a hired proposal to improve future cover letters';
  btn.addEventListener('mouseenter', () => { btn.style.background = '#15803d'; });
  btn.addEventListener('mouseleave', () => { btn.style.background = '#16a34a'; });
  btn.addEventListener('click', async () => {
    btn.textContent = 'Saving…';
    btn.style.cursor = 'default';
    try {
      const token = await _getAuthToken();
      if (!token) { btn.textContent = '✗ Not logged in'; setTimeout(() => btn.remove(), 3000); return; }
      const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
      // Job title: prefer the proposal job title heading, fall back to page title
      const titleEl = document.querySelector<HTMLElement>(
        '.qa-contract-title, h1.contract-title, [data-test="job-title"], h1'
      );
      const jobTitle = titleEl?.textContent?.trim() || document.title;
      const resp = await fetch(`${apiBase}/api/v1/proposals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({
          cover_letter_text: proposalText,
          upwork_job_url: window.location.href,
          job_title: jobTitle,
          was_hired: true,
          status: 'hired',
          source: 'contract_import',
        }),
        signal: AbortSignal.timeout(20_000),
      });
      if (resp.ok) {
        btn.style.background = '#15803d';
        btn.textContent = '✓ Proposal saved';
      } else {
        btn.textContent = `✗ Error ${resp.status}`;
      }
    } catch (err) {
      btn.textContent = `✗ ${String(err).substring(0, 30)}`;
    }
    setTimeout(() => { btn.remove(); _workroomProposalBtnInjected = false; }, 4000);
  });
  document.body.appendChild(btn);
}

// ---------------------------------------------------------------------------

interface ScrapedSavedSearch {
  query: string;
  url_params: string;
  label: string;
}

/**
 * Extract saved searches from Upwork's find-work or search pages.
 * Looks for links to /nx/search/jobs that contain a q= parameter.
 */
function extractSavedSearches(): ScrapedSavedSearch[] {
  const results: ScrapedSavedSearch[] = [];
  const seen = new Set<string>();

  const links = document.querySelectorAll<HTMLAnchorElement>('a[href*="/nx/search/jobs"]');
  links.forEach((link) => {
    try {
      const url = new URL(link.href);
      const q = url.searchParams.get('q');
      if (!q || !q.trim()) return;

      const normalized = q.trim().toLowerCase();
      if (seen.has(normalized)) return;
      seen.add(normalized);

      // Build url_params from remaining params (exclude q and nbs)
      const extra = new URLSearchParams(url.search);
      extra.delete('q');
      extra.delete('nbs');
      const urlParams = extra.toString();

      const label = link.textContent?.trim() || q.trim();
      results.push({ query: q.trim(), url_params: urlParams, label });
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
  console.log('UpApply: Received message', message.type, message);

  switch (message.type) {
    case 'EXTRACT_JOB_DATA':
      console.log('UpApply: EXTRACT_JOB_DATA received, isJobPage:', isJobPage(), 'URL:', window.location.href);
      if (!isJobPage()) {
        console.log('UpApply: Not a job page, returning error');
        sendResponse({ success: false, error: 'Not on a job page' });
        return true;
      }
      try {
        const jobData = extractJobData();
        console.log('UpApply: Extraction complete, title:', jobData.title);
        if (!jobData.title) {
          // Send debug info back so it's visible in the background/sidebar console
          const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5')).slice(0, 8);
          const debug = headings.map(h => `<${h.tagName} class="${h.className.substring(0, 40)}"> ${h.textContent?.trim().substring(0, 60)}`);
          console.log('UpApply: DEBUG headings:', debug);
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
        sendResponse(result);
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
            sendResponse({ success: true, data: proposals, url: window.location.href, debug: debugHits });
          } catch (err) {
            sendResponse({ success: false, error: String(err), debug: debugHits });
          }
        })();
        return true; // keep message channel open for async sendResponse
      }
      break;
    }

    case 'SCRAPE_JOB_CARDS': {
      if (!isJobCardPage()) {
        sendResponse({ success: false, error: 'Not on a job listings page', url: window.location.href });
      } else {
        (async () => {
          try {
            const cards = await extractAllJobCards();
            sendResponse({ success: true, data: cards, url: window.location.href });
          } catch (err) {
            sendResponse({ success: false, error: String(err) });
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
          const data = await _scrapeAllContracts();
          sendResponse({ success: true, data, url: window.location.href });
        } catch (err) {
          sendResponse({ success: false, error: String(err) });
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

  return true; // Keep message channel open for async response
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
  console.log('UpApply: Pending auto-fill found for job slug', urlSlug);

  const tryFill = (): boolean => fillCoverLetter(pending.coverLetter);

  // Try immediately; if form not rendered yet, wait via MutationObserver
  if (!tryFill()) {
    const observer = new MutationObserver(() => {
      if (tryFill()) {
        observer.disconnect();
        console.log('UpApply: Pending auto-fill applied via observer');
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    // Give up after 15 seconds
    setTimeout(() => observer.disconnect(), 15000);
  } else {
    console.log('UpApply: Pending auto-fill applied immediately');
  }
}

/**
 * Initialize content script.
 */
function init() {
  // Prevent duplicate init from re-injection
  if ((window as unknown as Record<string, unknown>)[INIT_FLAG]) {
    console.log('UpApply: Already initialized, skipping');
    return;
  }
  (window as unknown as Record<string, unknown>)[INIT_FLAG] = true;

  console.log('UpApply: Content script loaded on', window.location.href);

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
      console.log('UpApply: URL changed to', lastUrl);

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
