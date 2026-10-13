import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const noop = () => {};
  (globalThis as unknown as { chrome: unknown }).chrome = {
    runtime: { sendMessage: noop, onMessage: { addListener: noop }, lastError: undefined },
    storage: { local: { get: noop, set: noop, remove: noop } },
  };
});

vi.mock('../../lib/api-client', () => ({
  apiClient: { refineCoverLetter: vi.fn() },
}));

import { createElement } from 'react';
import { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { apiClient } from '../../lib/api-client';
import { useAppStore } from '../store';
import Generator from './Generator';

const refineMock = apiClient.refineCoverLetter as unknown as ReturnType<typeof vi.fn>;

let container: HTMLDivElement;
let root: Root;

function refineResult(letter: string, userMsg: string) {
  return {
    cover_letter: letter,
    screening_answers: [],
    warnings: ['old draft warning'],
    claims_verified: false,
    refine_messages: [
      { role: 'user', content: userMsg },
      { role: 'assistant', content: letter },
    ],
  };
}

async function sendRefine(message: string) {
  const input = container.querySelector<HTMLInputElement>('input[placeholder^="e.g."]')!;
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
  await act(async () => {
    setter.call(input, message);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  const send = [...container.querySelectorAll('button')].find(b => b.textContent?.trim() === 'Send')!;
  await act(async () => {
    send.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

function clickButton(label: string) {
  const btn = [...container.querySelectorAll('button')].find(b => b.textContent?.trim() === label);
  if (!btn) throw new Error(`button ${label} not found`);
  btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
}

beforeEach(() => {
  refineMock.mockReset();
  useAppStore.setState({
    currentJob: { title: 'Job', url: 'https://www.upwork.com/jobs/1', screeningQuestions: [], skills: [] } as never,
    coverLetter: 'Draft one.',
    coverLetterId: 'cl-1',
    coverLetterLoading: false,
    coverLetterError: null,
    draftMeta: { warnings: [], factsUsed: [], screeningAnswers: [], claimsVerified: true },
  });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('Generator refine chat', () => {
  it('drops a refine response that arrives after the active draft changed', async () => {
    let resolve!: (v: unknown) => void;
    refineMock.mockReturnValue(new Promise(r => { resolve = r; }));
    await act(async () => { root.render(createElement(Generator)); });

    await sendRefine('shorter');
    // A new draft replaces the one being refined while the request is in flight.
    await act(async () => {
      useAppStore.setState({ coverLetter: 'Draft two.', coverLetterId: 'cl-2' });
    });
    await act(async () => { resolve(refineResult('Refined draft one.', 'shorter')); });

    const state = useAppStore.getState();
    expect(state.coverLetter).toBe('Draft two.');
    expect(state.coverLetterId).toBe('cl-2');
    expect(state.draftMeta?.claimsVerified).toBe(true);
    expect(container.textContent).not.toContain('You: shorter');
    expect(container.textContent).not.toContain('old draft warning');
  });

  it('Generate All clears the previous draft refine thread', async () => {
    refineMock.mockResolvedValue(refineResult('Refined draft one.', 'shorter'));
    await act(async () => { root.render(createElement(Generator)); });
    await sendRefine('shorter');
    expect(container.textContent).toContain('You: shorter');

    // Back to the pre-draft view, then Generate All produces an unrelated draft.
    await act(async () => {
      useAppStore.setState({
        coverLetter: null,
        coverLetterId: null,
        jobAnalysis: {
          match_score: 80, recommendation: '', deal_breaker_warnings: [], strengths: [],
          concerns: [], skill_matches: [], missing_skills: [],
        },
        generateCoverLetter: async () => {
          useAppStore.setState({ coverLetter: 'Draft two.', coverLetterId: 'cl-2' });
        },
      } as never);
    });
    await act(async () => { clickButton('Generate All'); });

    expect(useAppStore.getState().coverLetterId).toBe('cl-2');
    expect(container.textContent).not.toContain('You: shorter');
    expect(container.textContent).not.toContain('old draft warning');
  });
});
