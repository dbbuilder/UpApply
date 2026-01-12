/**
 * Chrome storage utilities.
 */

export interface StorageData {
  authToken?: string;
  userProfile?: {
    id: string;
    email: string;
    has_profile: boolean;
  };
  currentJob?: {
    url: string;
    title: string;
    description: string;
    skills?: string[];
    budget?: string;
    clientInfo?: Record<string, string>;
  };
  lastAnalysis?: {
    match_score: number;
    recommendation: string;
    timestamp: number;
  };
}

export async function getStorageData<K extends keyof StorageData>(
  key: K
): Promise<StorageData[K] | undefined> {
  const result = await chrome.storage.local.get(key);
  return result[key];
}

export async function setStorageData<K extends keyof StorageData>(
  key: K,
  value: StorageData[K]
): Promise<void> {
  await chrome.storage.local.set({ [key]: value });
}

export async function removeStorageData(key: keyof StorageData): Promise<void> {
  await chrome.storage.local.remove(key);
}

export async function clearAllStorage(): Promise<void> {
  await chrome.storage.local.clear();
}

export async function isAuthenticated(): Promise<boolean> {
  const token = await getStorageData('authToken');
  return !!token;
}
