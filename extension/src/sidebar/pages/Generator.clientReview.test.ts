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
  apiClient: { generateCoverLetter: vi.fn() },
}));

import { createElement } from 'react';
import { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { apiClient } from '../../lib/api-client';
import { useAppStore } from '../store';
import Generator from './Generator';

const generateMock = apiClient.generateCoverLetter as unknown as ReturnType<typeof vi.fn>;

const initialState = useAppStore.getState();
let container: HTMLDivElement;
let root: Root;

const REVIEW = {
  shortlist: 'maybe',
  why: 'Credible, but the opening is generic.',
  paragraphs: [
    { paragraph: 1, verdict: 'rewrite', reason: 'Too vague about the cutover.' },
    { paragraph: 2, verdict: 'keep', reason: 'The migration proof lands.' },
  ],
};

function letter(clientReview: unknown = null) {
  return {
    id: 'cl-1', user_id: 'u1', job_id: 'j1', content: 'A letter.', model_used: 'm', version: 1,
    created_at: '2026-10-30T00:00:00Z', verify_warnings: [], facts_used: [], screening_answers: [],
    claims_verified: true, client_review: clientReview,
  };
}

function reviewCheckbox() {
  const label = [...container.querySelectorAll('label')].find(l => l.textContent?.includes("Client's-eye review"));
  if (!label) throw new Error('client review checkbox not found');
  return label.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
}

function clickButton(text: string) {
  const btn = [...container.querySelectorAll('button')].find(b => b.textContent?.trim() === text);
  if (!btn) throw new Error(`button ${text} not found`);
  btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
}

beforeEach(() => {
  generateMock.mockReset();
  useAppStore.setState({
    ...initialState,
    currentJob: {
      title: 'Azure SQL migration', description: 'Move our estate.', url: 'https://www.upwork.com/jobs/1',
      screeningQuestions: [], skills: [],
    } as never,
    jobAnalysis: {
      match_score: 80, recommendation: '', deal_breaker_warnings: [], strengths: [],
      concerns: [], skill_matches: [], missing_skills: [],
    } as never,
    coverLetter: null,
    coverLetterId: null,
    coverLetterLoading: false,
    coverLetterError: null,
    draftMeta: null,
  });
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("Generator client's-eye review", () => {
  it('is unchecked by default and sends client_review: false', async () => {
    generateMock.mockResolvedValue(letter());
    await act(async () => { root.render(createElement(Generator)); });
    expect(reviewCheckbox().checked).toBe(false);
    await act(async () => { clickButton('Cover Letter Only'); });
    expect(generateMock).toHaveBeenCalledTimes(1);
    expect(generateMock.mock.calls[0][0].client_review).toBe(false);
    expect(container.textContent).not.toContain("Client's-eye review:");
  });

  it('sends client_review: true when ticked and shows the verdict', async () => {
    generateMock.mockResolvedValue(letter(REVIEW));
    await act(async () => { root.render(createElement(Generator)); });
    await act(async () => { reviewCheckbox().click(); });
    expect(reviewCheckbox().checked).toBe(true);
    await act(async () => { clickButton('Cover Letter Only'); });
    expect(generateMock.mock.calls[0][0].client_review).toBe(true);
    expect(generateMock.mock.calls[0][0].include_call_offer).toBe(true);
    expect(useAppStore.getState().draftMeta?.clientReview).toEqual(REVIEW);
    expect(container.textContent).toContain("Client's-eye review: Maybe");
    expect(container.textContent).toContain('Credible, but the opening is generic.');
    expect(container.textContent).toContain('Paragraph 1: rewrite - Too vague about the cutover.');
  });
});
