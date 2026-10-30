import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.hoisted(() => {
  (globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

vi.mock('../../lib/api-client', () => ({
  apiClient: { getLearnedRules: vi.fn(), proposeLearnedRules: vi.fn(), decideLearnedRule: vi.fn() },
}));

import { createElement } from 'react';
import { act } from 'react';
import { createRoot, Root } from 'react-dom/client';
import { apiClient } from '../../lib/api-client';
import RulesPage from './RulesPage';

const listMock = apiClient.getLearnedRules as unknown as ReturnType<typeof vi.fn>;
const proposeMock = apiClient.proposeLearnedRules as unknown as ReturnType<typeof vi.fn>;
const decideMock = apiClient.decideLearnedRule as unknown as ReturnType<typeof vi.fn>;

const RULE = {
  id: 'r1',
  rule: 'End on a plain question to the client.',
  evidence_quote: 'Shall we talk through your estate?',
  times_seen: 2,
  status: 'proposed',
  created_at: '2026-10-30T00:00:00Z',
  decided_at: null,
};

let container: HTMLDivElement;
let root: Root;

async function render() {
  await act(async () => {
    root.render(createElement(RulesPage));
  });
}

async function click(label: string) {
  const btn = [...container.querySelectorAll('button')].find(b => b.textContent?.trim() === label);
  if (!btn) throw new Error(`button ${label} not found`);
  await act(async () => {
    btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

beforeEach(() => {
  listMock.mockReset();
  proposeMock.mockReset();
  decideMock.mockReset();
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('RulesPage', () => {
  it('lists proposed rules with their evidence', async () => {
    listMock.mockResolvedValue([RULE]);
    await render();
    expect(listMock).toHaveBeenCalledWith('proposed');
    expect(container.textContent).toContain(RULE.rule);
    expect(container.textContent).toContain(RULE.evidence_quote);
  });

  it('accepting removes the rule and shows the voice-kit note', async () => {
    listMock.mockResolvedValue([RULE]);
    decideMock.mockResolvedValue({ ...RULE, status: 'accepted', note: 'Copy this rule to chris/feedback-log.md' });
    await render();
    await click('Accept');
    expect(decideMock).toHaveBeenCalledWith('r1', 'accepted');
    expect(container.textContent).not.toContain(RULE.rule);
    expect(container.textContent).toContain('chris/feedback-log.md');
  });

  it('rejecting calls the API with rejected', async () => {
    listMock.mockResolvedValue([RULE]);
    decideMock.mockResolvedValue({ ...RULE, status: 'rejected', note: null });
    await render();
    await click('Reject');
    expect(decideMock).toHaveBeenCalledWith('r1', 'rejected');
    expect(container.textContent).toContain('Rule rejected.');
  });

  it('suggest proposes rules and reloads the review list', async () => {
    listMock.mockResolvedValueOnce([]).mockResolvedValueOnce([RULE]);
    proposeMock.mockResolvedValue({ proposed: [RULE], pairs_found: 3, refine_requests_found: 1 });
    await render();
    await click('Suggest rules from my edits');
    expect(proposeMock).toHaveBeenCalledOnce();
    expect(container.textContent).toContain('1 new rule from 3 edited letters and 1 refine request.');
    expect(container.textContent).toContain(RULE.rule);
  });

  it('accepted rules have no decision buttons', async () => {
    listMock.mockResolvedValue([{ ...RULE, status: 'accepted' }]);
    await render();
    await click('Accepted');
    expect(listMock).toHaveBeenLastCalledWith('accepted');
    expect([...container.querySelectorAll('button')].map(b => b.textContent)).not.toContain('Accept');
  });
});
