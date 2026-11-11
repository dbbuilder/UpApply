import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.stubGlobal('chrome', {
  storage: { local: { get: vi.fn(async () => ({})), set: vi.fn(), remove: vi.fn() }, onChanged: { addListener: vi.fn() } },
  runtime: { onMessage: { addListener: vi.fn() }, sendMessage: vi.fn() },
});

const { apiClient } = await import('../lib/api-client');
const { useAppStore } = await import('./store');

const job = (url: string) => ({
  url, title: 'CRM in Floot', description: 'Finish the CRM', skills: [], budgetType: null, budgetAmount: null,
  clientInfo: {}, screeningQuestions: [],
}) as never;

function pendingAnalysis() {
  let resolve!: (v: unknown) => void;
  let signal: AbortSignal | undefined;
  vi.spyOn(apiClient, 'analyzeJob').mockImplementation((_data, s) => {
    signal = s;
    return new Promise((r) => { resolve = r; }) as never;
  });
  return { finish: () => resolve({ match_score: 88 }), signal: () => signal };
}

describe('Cancel on "Analyzing job..."', () => {
  beforeEach(() => {
    useAppStore.setState({ currentJob: job('https://www.upwork.com/jobs/~021'), jobAnalysis: null,
      analysisLoading: false, analysisError: null } as never);
  });

  it('stops waiting, aborts the request and ignores the late reply', async () => {
    const run = pendingAnalysis();
    const done = useAppStore.getState().analyzeCurrentJob();
    expect(useAppStore.getState().analysisLoading).toBe(true);

    useAppStore.getState().cancelAnalysis();
    expect(useAppStore.getState().analysisLoading).toBe(false);
    expect(run.signal()?.aborted).toBe(true);

    run.finish();
    await done;
    expect(useAppStore.getState().jobAnalysis).toBeNull();
    expect(useAppStore.getState().analysisError).toBeNull();
  });

  it("moving to another job stops the old job's analysis", async () => {
    const run = pendingAnalysis();
    const done = useAppStore.getState().analyzeCurrentJob();
    useAppStore.getState().setCurrentJob(job('https://www.upwork.com/jobs/~022'));
    expect(useAppStore.getState().analysisLoading).toBe(false);
    run.finish();
    await done;
    expect(useAppStore.getState().jobAnalysis).toBeNull();
  });

  it('a finished analysis still lands when nothing cancelled it', async () => {
    const run = pendingAnalysis();
    const done = useAppStore.getState().analyzeCurrentJob();
    run.finish();
    await done;
    expect(useAppStore.getState().jobAnalysis).toEqual({ match_score: 88 });
    expect(useAppStore.getState().analysisLoading).toBe(false);
  });
});
