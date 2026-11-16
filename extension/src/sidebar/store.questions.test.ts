import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.stubGlobal('chrome', {
  storage: { local: { get: vi.fn(async () => ({})), set: vi.fn(), remove: vi.fn() }, onChanged: { addListener: vi.fn() } },
  runtime: { onMessage: { addListener: vi.fn() }, sendMessage: vi.fn() },
});
const { useAppStore } = await import('./store');

const JOB = 'https://www.upwork.com/jobs/Dev_~022120569342365685392/';
const APPLY = 'https://www.upwork.com/nx/proposals/job/~022120569342365685392/apply/';
const OTHER_APPLY = 'https://www.upwork.com/nx/proposals/job/~022119834819519015314/apply/';
const Q = [{ question: 'TypeScript, React and Postgres?', inputSelector: '[data-upapply-q="0"]' }];

describe('screening questions from the apply page', () => {
  beforeEach(() => {
    useAppStore.setState({
      currentJob: { url: JOB, title: 'CRM', description: 'd', skills: [], screeningQuestions: [], clientInfo: {} },
      coverLetter: 'My letter', jobAnalysis: { match_score: 77 },
    } as never);
  });

  it('attach to the same job without resetting the letter or the analysis', () => {
    useAppStore.getState().mergeScreeningQuestions(APPLY, Q);
    const s = useAppStore.getState();
    expect(s.currentJob?.screeningQuestions).toEqual(Q);
    expect(s.coverLetter).toBe('My letter');
    expect(s.jobAnalysis).toEqual({ match_score: 77 });
  });

  it("another job's questions are ignored", () => {
    useAppStore.getState().mergeScreeningQuestions(OTHER_APPLY, Q);
    expect(useAppStore.getState().currentJob?.screeningQuestions).toEqual([]);
  });
});
