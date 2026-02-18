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

  // Debug: Check if key elements exist
  const feJobDetails = document.querySelector('.fe-job-details');
  const feUiApplication = document.querySelector('.fe-ui-application-vue');
  console.log('UpApply: Page elements found:', {
    '.fe-job-details': !!feJobDetails,
    '.fe-ui-application-vue': !!feUiApplication,
    'any h3 in .fe-job-details': feJobDetails?.querySelector('h3')?.textContent?.substring(0, 50),
  });

  // Extract basic job info
  const title = extractText(SELECTORS.jobTitle);
  const description = extractText(SELECTORS.jobDescription);
  const skills = extractTexts(SELECTORS.skills);
  const experienceLevel = extractText(SELECTORS.experienceLevel);
  const projectLength = extractText(SELECTORS.projectLength);

  console.log('UpApply: Extraction results:', {
    title,
    descriptionLength: description?.length,
    skills,
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
  return window.location.href.includes('/jobs/') ||
         window.location.href.includes('/nx/proposals/');
}

/**
 * Check if we're on the My Proposals page.
 */
function isMyProposalsPage(): boolean {
  return window.location.href.includes('/freelancers/proposals') ||
         window.location.href.includes('/nx/find-work/proposals') ||
         window.location.href.includes('/ab/proposals');
}

/**
 * Extract proposals from the My Proposals page.
 */
function extractProposals(): ScrapedProposal[] {
  const proposals: ScrapedProposal[] = [];

  // Find all proposal items
  const proposalItems = querySelectorAll(SELECTORS.proposalListItem);
  console.log('UpApply: Found', proposalItems.length, 'proposal items');

  for (const item of proposalItems) {
    try {
      // Extract job title and URL
      const titleElement = item.querySelector('h4 a, .job-title-link, [data-test="proposal-job-title"]');
      const jobTitle = titleElement?.textContent?.trim() || null;
      const jobUrl = titleElement?.getAttribute('href') || null;

      // Try to get proposal ID from data attributes or URL
      const proposalId = item.getAttribute('data-proposal-id') ||
                         jobUrl?.match(/~([a-zA-Z0-9]+)/)?.[1] ||
                         null;

      // Extract cover letter - this might require expanding the proposal
      const coverLetterElement = item.querySelector('.cover-letter-text, [data-test="proposal-cover-letter"], .proposal-description');
      const coverLetter = coverLetterElement?.textContent?.trim() || null;

      // Extract bid amount
      const bidText = item.querySelector('.proposal-bid-amount, [data-test="proposal-bid"]')?.textContent?.trim();
      let bidAmount: number | null = null;
      let bidType: string | null = null;
      if (bidText) {
        const match = bidText.match(/\$?([\d,]+\.?\d*)/);
        if (match) {
          bidAmount = parseFloat(match[1].replace(',', ''));
        }
        bidType = bidText.toLowerCase().includes('/hr') || bidText.toLowerCase().includes('hourly')
          ? 'hourly' : 'fixed';
      }

      // Extract status
      const statusElement = item.querySelector('.status-badge, [data-test="proposal-status"], .proposal-status');
      const status = statusElement?.textContent?.trim()?.toLowerCase() || 'submitted';

      // Extract submitted date
      const dateElement = item.querySelector('time, [data-test="proposal-date"], .proposal-submitted-date');
      const submittedAt = dateElement?.getAttribute('datetime') ||
                          dateElement?.textContent?.trim() ||
                          null;

      if (jobTitle || coverLetter) {
        proposals.push({
          proposalId,
          jobTitle,
          jobUrl: jobUrl ? new URL(jobUrl, window.location.origin).href : null,
          coverLetter,
          bidAmount,
          bidType,
          status,
          submittedAt,
        });
      }
    } catch (err) {
      console.error('UpApply: Error extracting proposal:', err);
    }
  }

  return proposals;
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
        sendResponse({ success: true, data: jobData });
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

    case 'SCRAPE_PROPOSALS':
      if (!isMyProposalsPage()) {
        sendResponse({ success: false, error: 'Not on My Proposals page' });
      } else {
        try {
          const proposals = extractProposals();
          sendResponse({ success: true, data: proposals });
        } catch (err) {
          sendResponse({ success: false, error: String(err) });
        }
      }
      break;

    case 'GET_PAGE_TYPE':
      sendResponse({
        isJobPage: isJobPage(),
        isMyProposalsPage: isMyProposalsPage(),
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
 * Initialize content script.
 */
function init() {
  console.log('UpApply: Content script loaded on', window.location.href);

  // Notify background script that we're ready
  chrome.runtime.sendMessage({
    type: 'CONTENT_SCRIPT_READY',
    url: window.location.href,
    isJobPage: isJobPage(),
  });

  // If we're on a job page, extract and send initial data
  if (isJobPage()) {
    // Wait for dynamic content to load (proposal pages can be slower)
    setTimeout(() => {
      const jobData = extractJobData();
      console.log('UpApply: Extracted job data:', jobData);

      // Only send if we found something useful
      if (jobData.title || jobData.description) {
        chrome.runtime.sendMessage({
          type: 'JOB_DATA_EXTRACTED',
          data: jobData,
        });
      } else {
        console.log('UpApply: No job data found, retrying in 2s...');
        // Retry after more time for slow-loading pages
        setTimeout(() => {
          const retryData = extractJobData();
          console.log('UpApply: Retry extracted job data:', retryData);
          chrome.runtime.sendMessage({
            type: 'JOB_DATA_EXTRACTED',
            data: retryData,
          });
        }, 2000);
      }
    }, 1500);
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// Watch for SPA navigation
let lastUrl = window.location.href;
const observer = new MutationObserver(() => {
  if (window.location.href !== lastUrl) {
    lastUrl = window.location.href;
    console.log('UpApply: URL changed to', lastUrl);

    // Re-extract job data on navigation
    if (isJobPage()) {
      setTimeout(() => {
        const jobData = extractJobData();
        chrome.runtime.sendMessage({
          type: 'JOB_DATA_EXTRACTED',
          data: jobData,
        });
      }, 1000);
    }
  }
});

observer.observe(document.body, { childList: true, subtree: true });
