import { beforeEach, describe, expect, it, vi } from 'vitest';
import { loadInclusions, pruned, saveInclusions } from './job-inclusions';

let mem: Record<string, unknown> = {};
beforeEach(() => {
  mem = {};
  vi.stubGlobal('chrome', {
    storage: { local: {
      get: vi.fn(async (k: string) => ({ [k]: mem[k] })),
      set: vi.fn(async (o: Record<string, unknown>) => { Object.assign(mem, o); }),
    } },
  });
});

const JOB = 'https://www.upwork.com/jobs/~022120267556036166102';
const APPLY = 'https://www.upwork.com/nx/proposals/job/~022120267556036166102/apply/';
const OTHER = 'https://www.upwork.com/jobs/~022119834819519015314';

describe('per-job "Include in cover letter" text', () => {
  it('a new job starts empty; the same job (job or apply page) gets its text back', async () => {
    await saveInclusions(JOB, 'Built a full salon management system');
    expect(await loadInclusions(APPLY)).toBe('Built a full salon management system');
    expect(await loadInclusions(OTHER)).toBe('');
  });

  it('clearing the box forgets the job; pages without a job id are ignored', async () => {
    await saveInclusions(JOB, 'x');
    await saveInclusions(JOB, '   ');
    expect(await loadInclusions(JOB)).toBe('');
    await saveInclusions('https://www.upwork.com/nx/find-work/', 'y');
    expect(mem.jobInclusions).toEqual({});
  });

  it('keeps only the newest jobs', () => {
    const store = { a: { text: '1', at: 1 }, b: { text: '2', at: 3 }, c: { text: '3', at: 2 } };
    expect(Object.keys(pruned(store, 2)).sort()).toEqual(['b', 'c']);
  });
});
