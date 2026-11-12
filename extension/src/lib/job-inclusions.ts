import { jobIdFromUrl } from '../content/job-cards';

/**
 * "Include in cover letter" text, kept per Upwork job: a new job starts empty, and returning to
 * a job (its job page or its apply page share the ~0<id>) brings its text back. Stored in
 * chrome.storage.local, newest MAX_JOBS jobs only.
 */
const KEY = 'jobInclusions';
export const MAX_JOBS = 200;

type Store = Record<string, { text: string; at: number }>;

async function read(): Promise<Store> {
  try {
    const got = await chrome.storage.local.get(KEY);
    return (got?.[KEY] as Store) ?? {};
  } catch {
    return {};
  }
}

export async function loadInclusions(url: string | null | undefined): Promise<string> {
  const id = url ? jobIdFromUrl(url) : null;
  if (!id) return '';
  return (await read())[id]?.text ?? '';
}

export function pruned(store: Store, max = MAX_JOBS): Store {
  const keep = Object.entries(store).sort((a, b) => b[1].at - a[1].at).slice(0, max);
  return Object.fromEntries(keep);
}

export async function saveInclusions(url: string | null | undefined, text: string, now = Date.now()): Promise<void> {
  const id = url ? jobIdFromUrl(url) : null;
  if (!id) return;
  const store = await read();
  if (text.trim()) store[id] = { text, at: now };
  else delete store[id];
  try {
    await chrome.storage.local.set({ [KEY]: pruned(store) });
  } catch {
    // Storage unavailable: the text still works for this session, it just is not remembered.
  }
}
