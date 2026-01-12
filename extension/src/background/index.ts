/**
 * Background service worker for UpApply extension.
 * Handles communication between content scripts and sidebar.
 */

// Store current job data for sidebar access
let currentJobData: JobData | null = null;

interface JobData {
  url: string;
  title: string | null;
  description: string | null;
  budgetType: string | null;
  budgetAmount: string | null;
  skills: string[];
  experienceLevel: string | null;
  projectLength: string | null;
  clientInfo: {
    rating: string | null;
    location: string | null;
    totalSpent: string | null;
    hireRate: string | null;
  };
}

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
  }

  return false;
});

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
