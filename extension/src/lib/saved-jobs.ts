import type { JobImportItem } from './api-client';

/** Saved jobs posted within this many days go to the Queue; older ones are kept as a signal only. */
export const SAVED_JOBS_QUEUE_DAYS = 14;
/** Saved jobs per import request: the server embeds each one, so a 500-save list goes in steps. */
export const SAVED_IMPORT_BATCH = 25;

export interface SavedJobCard {
  upworkJobId: string;
  upworkUrl: string;
  title: string;
  description: string;
  jobType?: string | null;
  experienceLevel?: string | null;
  postedDateRaw?: string | null;
  clientInfo?: Record<string, unknown>;
}

/** Days since an Upwork "Posted …" string; 0 when unknown (treated as recent). */
export function parseDaysAgo(raw: string | null | undefined): number {
  if (!raw) return 0;
  const s = raw.toLowerCase();
  if (s.includes('just now') || s.includes('minute') || s.includes('hour')) return 0;
  if (s.includes('yesterday')) return 1;
  if (s.includes('last week')) return 7;
  const daysMatch = s.match(/(\d+)\s*day/);
  if (daysMatch) return parseInt(daysMatch[1], 10);
  const weeksMatch = s.match(/(\d+)\s*week/);
  if (weeksMatch) return parseInt(weeksMatch[1], 10) * 7;
  if (s.includes('month') || s.includes('year')) return 999;
  return 0;
}

/** Every saved card becomes an import item: recent ones are analysed and queued, older ones are
 *  stored with signal_only (a preference signal for scoring and searches, never queued). */
export function savedImportItems(cards: SavedJobCard[]): JobImportItem[] {
  return cards.map((c) => ({
    upwork_job_id: c.upworkJobId,
    upwork_url: c.upworkUrl,
    title: c.title,
    description: c.description,
    job_type: c.jobType ?? undefined,
    experience_level: c.experienceLevel ?? undefined,
    posted_date_raw: c.postedDateRaw ?? undefined,
    client_info: c.clientInfo,
    signal_only: parseDaysAgo(c.postedDateRaw) > SAVED_JOBS_QUEUE_DAYS,
  }));
}

export function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}
