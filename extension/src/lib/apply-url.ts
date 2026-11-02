/**
 * Upwork's proposal form for a job lives at /nx/proposals/job/~<id>/apply/.
 * Appending "/apply" to the job URL (/jobs/~<id>/apply) is not a real page.
 * Falls back to the job URL itself when it carries no ~<id>.
 */
export function upworkApplyUrl(jobUrl: string): string {
  const jobSlug = jobUrl?.match(/(~[a-zA-Z0-9]+)/)?.[1];
  return jobSlug ? `https://www.upwork.com/nx/proposals/job/${jobSlug}/apply/` : jobUrl;
}
