/**
 * Page matchers for privileged content-script actions (submit capture, outcome sync).
 * Pass `location.pathname` only: a query string or fragment must never satisfy a match
 * (e.g. /messages?next=/apply). Patterns are anchored to the real Upwork URLs:
 *   apply page      /nx/proposals/job/~<slug>/apply/
 *   proposals list  /nx/proposals/ and /nx/proposals/archived
 */
const APPLY_PATH = /^\/nx\/proposals\/job\/~[A-Za-z0-9]+\/apply\/?$/;
const PROPOSALS_LIST_PATH = /^\/nx\/proposals(?:\/archived)?\/?$/;

export function isApplyPage(pathname: string): boolean {
  return APPLY_PATH.test(pathname);
}

export function isProposalsListPage(pathname: string): boolean {
  return PROPOSALS_LIST_PATH.test(pathname);
}
