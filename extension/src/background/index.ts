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
            if (chrome.runtime.lastError) {
              console.error('UpApply Background: Error:', chrome.runtime.lastError);
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
              sendResponse(response || { success: false, error: 'No response' });
            }
          });
        }, 200);
      });
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

// Listen for tab updates to extract job data on Upwork pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url?.includes('upwork.com')) {
    // Request job data from content script
    chrome.tabs.sendMessage(tabId, { type: 'EXTRACT_JOB_DATA' }).catch(() => {
      // Content script might not be loaded yet
    });
  }
});

console.log('UpApply Background: Service worker started');
