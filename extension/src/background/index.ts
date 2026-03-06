/**
 * Background service worker for UpApply extension.
 * Handles communication between content scripts and sidebar.
 */
import type { JobData } from '../types';

// Store current job data for sidebar access
let currentJobData: JobData | null = null;

// Listen for messages from content script and sidebar
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('UpApply Background: Received message', message.type);

  switch (message.type) {
    case 'CONTENT_SCRIPT_READY':
      console.log('Content script ready on', message.url);
      break;

    case 'JOB_DATA_EXTRACTED':
      currentJobData = message.data;
      console.log('Job data extracted:', currentJobData?.title);

      // Store in local storage for sidebar access
      chrome.storage.local.set({ currentJob: currentJobData });

      // Notify sidebar if it's open
      chrome.runtime.sendMessage({
        type: 'JOB_DATA_UPDATED',
        data: currentJobData,
      }).catch(() => {
        // Sidebar might not be open
      });
      break;

    case 'GET_CURRENT_JOB':
      sendResponse({ data: currentJobData });
      break;

    case 'REQUEST_JOB_EXTRACTION':
      // Forward extraction request to content script in active tab
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        console.log('UpApply Background: Requesting extraction from tab', tab?.id, tab?.url);

        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if not already loaded
        try {
          // Get content script path from manifest
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
            console.log('UpApply Background: Content script injected:', contentScriptPath);
          }
        } catch (e) {
          console.log('UpApply Background: Script injection note:', e);
        }

        // Small delay to let script initialize
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'EXTRACT_JOB_DATA' }, (response) => {
            console.log('UpApply Background: Extraction response:', response);
            if (response?.debug) {
              console.log('UpApply Background: DEBUG - page headings:', response.debug);
            }
            if (chrome.runtime.lastError) {
              console.error('UpApply Background: Error:', chrome.runtime.lastError.message);
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the Upwork page and try again.' });
            } else if (response?.success) {
              currentJobData = response.data;
              chrome.storage.local.set({ currentJob: currentJobData });
              sendResponse(response);
            } else {
              sendResponse(response || { success: false, error: 'No response from content script' });
            }
          });
        }, 200);
      });
      return true; // Keep channel open for async response

    case 'FILL_COVER_LETTER':
      // Forward to content script in active tab (with injection if needed)
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if not already loaded
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
            console.log('UpApply Background: Content script injected for fill');
          }
        } catch (e) {
          console.log('UpApply Background: Script injection note:', e);
        }

        // Small delay to let script initialize
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_COVER_LETTER',
            content: message.content,
          }, (response) => {
            if (chrome.runtime.lastError) {
              console.error('UpApply Background: Fill error:', chrome.runtime.lastError);
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true; // Keep channel open for async response

    case 'SET_BID_AMOUNT':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'SET_BID_AMOUNT',
            amount: message.amount,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'FILL_SCREENING_QUESTION':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, {
            type: 'FILL_SCREENING_QUESTION',
            selector: message.selector,
            answer: message.answer,
          }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              sendResponse(response || { success: false });
            }
          });
        }, 200);
      });
      return true;

    case 'OPEN_SIDEBAR':
      if (sender.tab?.windowId) {
        chrome.sidePanel.open({ windowId: sender.tab.windowId });
      }
      break;

    case 'SCRAPE_PROPOSALS':
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }

        // Try to inject content script if needed
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              files: [contentScriptPath]
            });
          }
        } catch (e) {
          // Script may already be loaded
        }

        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_PROPOSALS' }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh the page.' });
            } else {
              if (response?.debug?.length) {
                console.log('UpApply Proposals debug — selectors that matched: ' + response.debug.join(' | '));
              }
              console.log('UpApply Proposals scrape result:', response?.success, '— found', response?.data?.length ?? 0, 'proposals', 'url:', response?.url);
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true;

    case 'SCRAPE_JOB_CARDS':
      // Forward to active tab's content script (user should be on saved jobs or search page)
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id || !tab?.url?.includes('upwork.com')) {
          sendResponse({ success: false, error: 'Not on an Upwork page' });
          return;
        }
        try {
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [contentScriptPath] });
          }
        } catch (e) { /* already loaded */ }
        setTimeout(() => {
          chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_JOB_CARDS' }, (response) => {
            if (chrome.runtime.lastError) {
              sendResponse({ success: false, error: 'Content script not loaded. Please refresh.' });
            } else {
              console.log('UpApply Job cards scrape:', response?.success, '—', response?.data?.length ?? 0, 'cards');
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
      return true;

    case 'IMPORT_SAVED_JOBS':
      // Navigate to saved jobs page in background tab, scrape, close, return cards
      (async () => {
        const savedUrl = 'https://www.upwork.com/nx/search/jobs/saved/';
        console.log('UpApply Background: Opening saved jobs tab:', savedUrl);
        const savedTab = await chrome.tabs.create({ url: savedUrl, active: false });
        if (!savedTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(savedTab.id);
          await new Promise(resolve => setTimeout(resolve, 2000));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: savedTab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(savedTab.id!, { type: 'SCRAPE_JOB_CARDS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(savedTab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'IMPORT_PROPOSALS':
      // Navigate to proposals page in background tab, scrape all proposals, close, return
      (async () => {
        const proposalsUrl = 'https://www.upwork.com/nx/find-work/proposals';
        console.log('UpApply Background: Opening proposals tab:', proposalsUrl);
        const propTab = await chrome.tabs.create({ url: proposalsUrl, active: false });
        if (!propTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(propTab.id);
          await new Promise(resolve => setTimeout(resolve, 2500));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: propTab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string; debug?: string[] }>((resolve) => {
            chrome.tabs.sendMessage(propTab.id!, { type: 'SCRAPE_PROPOSALS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          if (response?.debug?.length) {
            console.log('UpApply Proposals debug:', response.debug.join(' | '));
          }
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(propTab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'IMPORT_UPWORK_SAVED_SEARCHES':
      // Navigate to Upwork find-work page in background tab, scrape saved searches, close tab
      (async () => {
        const findWorkUrl = 'https://www.upwork.com/nx/find-work/';
        console.log('UpApply Background: Opening find-work tab for saved searches:', findWorkUrl);
        const findWorkTab = await chrome.tabs.create({ url: findWorkUrl, active: false });
        if (!findWorkTab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(findWorkTab.id);
          await new Promise(resolve => setTimeout(resolve, 2500));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: findWorkTab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(findWorkTab.id!, { type: 'SCRAPE_SAVED_SEARCHES' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(findWorkTab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'SEARCH_UPWORK_JOBS':
      // Open a background tab, scrape search results, close tab, return cards
      (async () => {
        const query = encodeURIComponent(message.query || '');
        const extraParams = message.urlParams ? `&${message.urlParams}` : '';
        const searchUrl = `https://www.upwork.com/nx/search/jobs/?q=${query}&sort=recency${extraParams}`;
        console.log('UpApply Background: Opening search tab for:', searchUrl);
        const tab = await chrome.tabs.create({ url: searchUrl, active: false });
        if (!tab.id) { sendResponse({ success: false, error: 'Failed to create tab' }); return; }
        try {
          await waitForTabLoad(tab.id);
          await new Promise(resolve => setTimeout(resolve, 2000));
          const manifest = chrome.runtime.getManifest();
          const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
          if (contentScriptPath) {
            try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [contentScriptPath] }); }
            catch (e) { /* already loaded */ }
          }
          await new Promise(resolve => setTimeout(resolve, 500));
          const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
            chrome.tabs.sendMessage(tab.id!, { type: 'SCRAPE_JOB_CARDS' }, (resp) => {
              if (chrome.runtime.lastError) resolve({ success: false, error: chrome.runtime.lastError.message });
              else resolve(resp || { success: false, error: 'No response' });
            });
          });
          sendResponse(response);
        } finally {
          try { await chrome.tabs.remove(tab.id); } catch (e) { /* ignore */ }
        }
      })();
      return true;

    case 'GET_VIEW_POSTING_LINK':
      // Forward to content script in active tab
      chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
        const tab = tabs[0];
        if (!tab?.id) {
          sendResponse({ success: false, error: 'No active tab' });
          return;
        }

        chrome.tabs.sendMessage(tab.id, { type: 'GET_VIEW_POSTING_LINK' }, (response) => {
          if (chrome.runtime.lastError) {
            sendResponse({ success: false, error: 'Content script not loaded' });
          } else {
            sendResponse(response || { success: false });
          }
        });
      });
      return true;

    case 'EXTRACT_FULL_JOB':
      // Open the job posting in a background tab and extract data
      (async () => {
        try {
          const data = await extractFullJobInBackground(message.jobPostingUrl);
          sendResponse({ success: true, data });
        } catch (err) {
          console.error('UpApply Background: Full job extraction failed:', err);
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;

    case 'DOWNLOAD_ATTACHMENT':
      // Download an attachment and return as base64
      (async () => {
        try {
          const result = await downloadAttachment(message.url);
          sendResponse({ success: true, ...result });
        } catch (err) {
          console.error('UpApply Background: Attachment download failed:', err);
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;

    case 'SCORE_NOTIFICATION_JOB':
      // Open job URL in background tab, extract description, score via API, return score.
      // Results are cached in chrome.storage for 24 h to avoid re-scraping the same URL.
      (async () => {
        try {
          const { jobUrl, title } = message as { jobUrl: string; title: string };

          // --- Cache check ---
          const cacheKey = `sc_${jobUrl}`;
          const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 h
          const cacheStore = await chrome.storage.local.get(cacheKey);
          const cached = cacheStore[cacheKey] as { score: number; chips: string[]; ts: number } | undefined;
          if (cached && Date.now() - cached.ts < CACHE_TTL) {
            sendResponse({ success: true, score: cached.score, chips: cached.chips, cached: true });
            return;
          }

          const stored = await chrome.storage.local.get('authToken');
          const token = stored.authToken as string | undefined;
          if (!token) { sendResponse({ success: false, error: 'Not logged in' }); return; }

          // Open job page in background tab and extract description
          const tab = await chrome.tabs.create({ url: jobUrl, active: false });
          if (!tab.id) { sendResponse({ success: false, error: 'Tab creation failed' }); return; }

          let description = '';
          let budgetAmount: string | null = null;
          let budgetType: string | null = null;
          try {
            await waitForTabLoad(tab.id);
            await new Promise(resolve => setTimeout(resolve, 1500));
            const manifest = chrome.runtime.getManifest();
            const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
            if (contentScriptPath) {
              try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: [contentScriptPath] }); } catch { /* already loaded */ }
            }
            await new Promise(resolve => setTimeout(resolve, 500));
            const resp = await new Promise<{ success: boolean; data?: { fullDescription?: string | null; budgetAmount?: string | null; budgetType?: string | null } }>((resolve) => {
              chrome.tabs.sendMessage(tab.id!, { type: 'EXTRACT_JOB_POSTING_DATA' }, (r) => {
                if (chrome.runtime.lastError) resolve({ success: false });
                else resolve(r || { success: false });
              });
            });
            description = resp.data?.fullDescription || '';
            budgetAmount = resp.data?.budgetAmount ?? null;
            budgetType = resp.data?.budgetType ?? null;
          } finally {
            try { await chrome.tabs.remove(tab.id); } catch { /* ignore */ }
          }

          const apiBase = (import.meta.env as Record<string, string>)['VITE_API_URL'] || 'https://upapply-api.onrender.com';
          const analyzeResp = await fetch(`${apiBase}/api/v1/jobs/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ title: title || 'Job', description: description || title }),
          });

          if (!analyzeResp.ok) { sendResponse({ success: false, error: `API ${analyzeResp.status}` }); return; }
          const data = await analyzeResp.json() as { match_score: number };

          const chips = detectNotifChips(title, description, budgetAmount, budgetType);

          // Cache result
          await chrome.storage.local.set({ [cacheKey]: { score: data.match_score, chips, ts: Date.now() } });

          sendResponse({ success: true, score: data.match_score, chips });
        } catch (err) {
          sendResponse({ success: false, error: String(err) });
        }
      })();
      return true;
  }

  return false;
});

/**
 * Wait for a tab to complete loading.
 */
function waitForTabLoad(tabId: number, timeoutMs = 30000): Promise<void> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error('Tab load timeout'));
    }, timeoutMs);

    const listener = (id: number, changeInfo: chrome.tabs.TabChangeInfo) => {
      if (id === tabId && changeInfo.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        clearTimeout(timeout);
        resolve();
      }
    };

    chrome.tabs.onUpdated.addListener(listener);
  });
}

/**
 * Extract full job data by opening the job posting in a background tab.
 */
async function extractFullJobInBackground(jobPostingUrl: string): Promise<{
  fullDescription: string | null;
  attachments: Array<{ url: string; filename: string; contentType: string }>;
}> {
  console.log('UpApply Background: Opening background tab for:', jobPostingUrl);

  // Create background tab (not active)
  const tab = await chrome.tabs.create({
    url: jobPostingUrl,
    active: false,
  });

  if (!tab.id) {
    throw new Error('Failed to create tab');
  }

  try {
    // Wait for tab to load
    await waitForTabLoad(tab.id);

    // Additional delay for dynamic content
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Inject content script if needed
    const manifest = chrome.runtime.getManifest();
    const contentScriptPath = manifest.content_scripts?.[0]?.js?.[0];
    if (contentScriptPath) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: [contentScriptPath],
        });
        console.log('UpApply Background: Content script injected into background tab');
      } catch (e) {
        console.log('UpApply Background: Script injection note:', e);
      }
    }

    // Small delay after injection
    await new Promise(resolve => setTimeout(resolve, 500));

    // Extract data from the tab
    const response = await new Promise<{ success: boolean; data?: unknown; error?: string }>((resolve) => {
      chrome.tabs.sendMessage(tab.id!, { type: 'EXTRACT_JOB_POSTING_DATA' }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { success: false, error: 'No response' });
        }
      });
    });

    if (!response.success) {
      throw new Error(response.error || 'Extraction failed');
    }

    console.log('UpApply Background: Full job extracted successfully');
    return response.data as {
      fullDescription: string | null;
      attachments: Array<{ url: string; filename: string; contentType: string }>;
    };
  } finally {
    // Always close the background tab
    try {
      await chrome.tabs.remove(tab.id);
      console.log('UpApply Background: Background tab closed');
    } catch (e) {
      console.error('UpApply Background: Failed to close tab:', e);
    }
  }
}

/**
 * Download an attachment and return as base64.
 * This runs in the background context which may have different CORS restrictions.
 */
async function downloadAttachment(url: string): Promise<{ data: string; contentType: string; size: number }> {
  console.log('UpApply Background: Downloading attachment:', url);

  const response = await fetch(url, {
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const contentType = response.headers.get('content-type') || 'application/octet-stream';

  // Convert to base64
  const arrayBuffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  const base64 = btoa(binary);

  return {
    data: base64,
    contentType,
    size: blob.size,
  };
}

// Handle extension icon click - open sidebar
chrome.action.onClicked.addListener((tab) => {
  if (tab.windowId !== undefined) {
    chrome.sidePanel.open({ windowId: tab.windowId });
  }
});

// Set up side panel behavior
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

// Debounce extraction per tab to avoid duplicate EXTRACT_JOB_DATA messages
const pendingExtractions = new Map<number, ReturnType<typeof setTimeout>>();

// Listen for tab updates to extract job data on Upwork job pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  const url = tab.url ?? '';
  const isJobUrl = url.includes('upwork.com') && url.includes('/jobs/');
  if (changeInfo.status === 'complete' && isJobUrl) {
    // Cancel any pending extraction for this tab
    const existing = pendingExtractions.get(tabId);
    if (existing) clearTimeout(existing);

    // Delay extraction to let SPA content render (avoids null title)
    const timer = setTimeout(() => {
      pendingExtractions.delete(tabId);
      chrome.tabs.sendMessage(tabId, { type: 'EXTRACT_JOB_DATA' }, (response) => {
        if (chrome.runtime.lastError) return; // Content script not loaded
        if (response?.success && response.data) {
          currentJobData = response.data;
          chrome.storage.local.set({ currentJob: currentJobData });
          chrome.runtime.sendMessage({
            type: 'JOB_DATA_UPDATED',
            data: currentJobData,
          }).catch(() => {});
        }
      });
    }, 2000);
    pendingExtractions.set(tabId, timer);
  }
});

console.log('UpApply Background: Service worker started');

// ---------------------------------------------------------------------------
// Notification chip detection
// ---------------------------------------------------------------------------

function detectNotifChips(
  title: string,
  description: string,
  budgetAmount: string | null,
  budgetType: string | null,
): string[] {
  const text = `${title} ${description}`;
  const lower = text.toLowerCase();
  const chips: string[] = [];

  // Domain/tech keywords
  if (/\bmvp\b|minimum viable product/i.test(text))                          chips.push('MVP');
  if (/\bsaas\b|software.as.a.service/i.test(text))                          chips.push('SaaS');
  if (/\bazure\b/i.test(text))                                                chips.push('Azure');
  if (/\bsql\b|postgresql|mysql|sql\s*server|sqlite|nosql|mongodb/i.test(text)) chips.push('SQL');

  // "Role" — long-term position signals
  if (/\b(role|position|full[- ]?time|part[- ]?time|ongoing|retainer|staff)\b/.test(lower)) chips.push('Role');

  // Budget chip — prefer extracted values from DOM, fall back to regex on text
  if (budgetAmount) {
    const clean = budgetAmount.trim();
    if (budgetType === 'hourly') {
      chips.push(clean.includes('/hr') || clean.includes('/hour') ? clean : `${clean}/hr`);
    } else if (budgetType === 'fixed') {
      chips.push(clean);
    } else {
      chips.push(clean);
    }
  } else {
    // Fallback: scan description text for dollar amounts
    const hrMatch = text.match(/\$[\d,]+(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?\s*\/\s*h(?:r|our)/i);
    if (hrMatch) {
      chips.push(hrMatch[0].replace(/\s+/g, ''));
    } else {
      const fixedMatch = text.match(/\$[\d,]{2,}(?:\.\d+)?(?:\s*[-–]\s*\$[\d,]+(?:\.\d+)?)?(?!\s*\/)/);
      if (fixedMatch) chips.push(fixedMatch[0].replace(/\s+/g, ''));
    }
  }

  return chips;
}
