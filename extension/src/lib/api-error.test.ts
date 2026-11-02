import { describe, expect, it, vi } from 'vitest';

vi.stubGlobal('chrome', { storage: { local: { get: vi.fn(async () => ({})), set: vi.fn() } }, runtime: { id: 'x' } });
const { errorDetailText } = await import('./api-client');

describe('errorDetailText', () => {
  it('reads FastAPI validation lists instead of printing [object Object]', () => {
    expect(errorDetailText([{ loc: ['body', 'jobs', 3, 'title'], msg: 'String should have at most 300 characters', type: 'x' }]))
      .toBe('jobs.3.title: String should have at most 300 characters');
    expect(errorDetailText(Array.from({ length: 5 }, () => ({ loc: ['body', 'q'], msg: 'bad' }))))
      .toBe('q: bad; q: bad; q: bad (+2 more)');
  });

  it('passes strings through and stringifies other objects', () => {
    expect(errorDetailText('Rate limit exceeded')).toBe('Rate limit exceeded');
    expect(errorDetailText({ error: 'x' })).toBe('{"error":"x"}');
    expect(errorDetailText(undefined)).toBe('');
  });
});
