# Plan: Sidebar Navigation Redesign — Workflow-Oriented Bottom Nav

**Author:** Chris Therriault
**Date:** 2026-03-08
**Status:** Ready to implement
**Priority:** High — current nav is fragmented; users lose context and can't see options from sub-pages

---

## Problem Statement

The current sidebar navigation has two major flaws:

1. **Context loss**: Nav tabs only exist on the Generator page. Every other page (`History`, `Analytics`, `Skills`, `Memories`, `EditProfile`) shows only a `← Back` button. Users can't tell where they are or jump between sections without going back first.

2. **No workflow framing**: 8 flat pages (`generator`, `memories`, `history`, `analytics`, `feedback`, `skills`, `profile`, `setup`) with no grouping. There's no guidance for new users on what to do first, or for existing users on which tool serves which purpose.

---

## Design Principle

Reorganise around **4 workflow modes** visible at all times via a persistent bottom navigation bar — the same pattern used by well-designed mobile apps and modern Chrome extension sidebars:

```
┌──────────────────────────────┐
│                              │
│   Page content scrolls here  │
│                              │
│                              │
├──────────────────────────────┤
│  👤 Me  🔍 Find  ✍ Apply  📊 Track  │  ← always visible
└──────────────────────────────┘
```

---

## The 4 Modes

| Mode | Icon | Label | Purpose | Sub-pages |
|------|------|-------|---------|-----------|
| **Me** | 👤 | Me | Profile, skills, experience — who I am | Profile · Skills · Memories |
| **Find** | 🔍 | Find | Browse and filter scored jobs | Scored Jobs (new) |
| **Apply** | ✍️ | Apply | Generate cover letter for current Upwork job | Generator (existing) |
| **Track** | 📊 | Track | Pipeline, history, trends | Dashboard · History · Trends |

**Apply** auto-activates whenever the user navigates to a job page on Upwork (existing content script detection).

---

## Navigation Behaviour

### Bottom nav (persistent)
- Always rendered — survives page transitions
- Active mode highlighted: green underline + bold label + slightly brighter icon
- Tap icon: jump to that mode's default page (or remembered last sub-page)
- Badge on **Find**: number of jobs scored this session (e.g. `🔍 Find ①`)
- Badge on **Apply**: dot indicator when a job is detected on the current tab

### Me mode — inline sub-nav
When in "Me" mode, a horizontal pill-nav appears at the top of the content area:
```
[● Profile]  [ Skills]  [ Memories]
```
No full-page navigation needed — switching sub-pages is instant and context stays in "Me".

### Apply mode — no sub-nav
Generator is the only view. Header simplifies to just the UpApply wordmark + score badge for current job.

### Track mode — inline sub-nav
```
[● Pipeline]  [ History]  [ Trends]
```
Matches the Dashboard plan (3 tabs).

### Find mode — no sub-nav
Single view: Scored Jobs list with filter chips.

---

## AppShell Component

New component `extension/src/sidebar/AppShell.tsx` wraps all authenticated pages:

```tsx
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-screen bg-gray-50">
      <div className="flex-1 overflow-auto min-h-0">
        {children}
      </div>
      <PersistentNav />
    </div>
  );
}
```

`App.tsx` wraps the rendered view:
```tsx
return (
  <AppShell>
    {renderView()}
  </AppShell>
);
```

---

## PersistentNav Component

```tsx
const NAV_ITEMS: NavItem[] = [
  {
    mode: 'me',
    label: 'Me',
    icon: '👤',
    defaultView: 'profile',
    views: ['profile', 'skills', 'memories', 'setup'],
  },
  {
    mode: 'find',
    label: 'Find',
    icon: '🔍',
    defaultView: 'scored',
    views: ['scored'],
    badge: scoredCount > 0 ? String(scoredCount) : undefined,
  },
  {
    mode: 'apply',
    label: 'Apply',
    icon: '✍️',
    defaultView: 'generator',
    views: ['generator'],
    dot: hasJobDetected,
  },
  {
    mode: 'track',
    label: 'Track',
    icon: '📊',
    defaultView: 'history',
    views: ['history', 'analytics', 'feedback'],
  },
];
```

Visual specs:
- Height: 56px fixed
- Each item: `flex-1 flex-col items-center justify-center gap-0.5`
- Icon: 20px emoji or SVG
- Label: 10px, `font-medium`
- Active: `text-emerald-600` + `border-t-2 border-emerald-500`
- Inactive: `text-gray-400`
- Badge: 14px green pill top-right of icon
- Dot: 6px green dot top-right of icon

---

## Me Mode — Page Redesign

Current: `EditProfile.tsx`, `Skills.tsx`, `Memories.tsx` are 3 separate full-page views each with `← Back` header.

New: Single `MePage.tsx` with sub-nav:
```
[● Profile]  [ Skills]  [ Memories]
```

The Profile sub-tab replaces `EditProfile.tsx` — shows the collapsible profile sections (Identity, Goals, Preferences, Dealbreakers, Pricing). Skills and Memories are the existing pages but rendered inside the `MePage` shell without the `← Back` header.

**No more separate `EditProfile.tsx`, `Skills.tsx`, `Memories.tsx` routes** — they become sub-views of Me mode.

---

## Apply Mode — Header Simplification

Remove the current 2-tier Generator header (logo + 5 nav tabs). Replace with:

```
┌──────────────────────────────┐
│  UpApply    [Job Title...]  ▸ │
│             Score: 87  AI React│
└──────────────────────────────┘
```

- Left: wordmark
- Center: truncated job title (click to expand full title)
- Right: score badge for current job (if scored from notification)
- No nav tabs — those are in the bottom nav

---

## Track Mode — Sub-nav

```
[● Pipeline]  [ History]  [ Trends]
```

- Pipeline: funnel (from Dashboard plan)
- History: timeline (from Dashboard plan)
- Trends: charts (from Dashboard plan)

`Analytics.tsx` is renamed/replaced by `TrackPage.tsx` with the 3 sub-tabs.

---

## View Routing Changes

| Current route | New location |
|--------------|-------------|
| `generator` | Apply mode → Apply |
| `profile` | Me mode → Profile sub-tab |
| `skills` | Me mode → Skills sub-tab |
| `memories` | Me mode → Memories sub-tab |
| `setup` | Me mode → first run (Profile sub-tab, wizard overlay) |
| `history` | Track mode → History sub-tab |
| `analytics` | Track mode → Pipeline sub-tab (default) |
| `feedback` | Track mode → (footer link inside any Track sub-tab) |
| `scored` _(new)_ | Find mode |

The `store.currentView` type union expands to include `'scored'` and `'me'` | `'find'` | `'apply'` | `'track'`. Sub-tab state is stored in each mode's own local state (not in global store).

---

## Files to Create / Modify

### New files
| File | Purpose |
|------|---------|
| `extension/src/sidebar/AppShell.tsx` | Persistent wrapper with bottom nav |
| `extension/src/sidebar/components/PersistentNav.tsx` | Bottom nav bar |
| `extension/src/sidebar/pages/MePage.tsx` | Me mode: Profile/Skills/Memories tabs |
| `extension/src/sidebar/pages/FindPage.tsx` | Find mode: Scored Jobs (= ScoredJobs from previous plan) |
| `extension/src/sidebar/pages/TrackPage.tsx` | Track mode: Pipeline/History/Trends tabs |

### Modified files
| File | Change |
|------|--------|
| `extension/src/sidebar/App.tsx` | Wrap with AppShell; route `'me'`, `'find'`, `'apply'`, `'track'`; remove back-button views |
| `extension/src/sidebar/store.ts` | Add `'scored'`, `'me'`, `'find'`, `'track'` to ViewType; remove `'analytics'` as top-level |
| `extension/src/sidebar/pages/Generator.tsx` | Remove 5-tab nav + logo header; add simplified 1-line header |
| `extension/src/sidebar/pages/Analytics.tsx` | Absorbed into TrackPage (delete when TrackPage done) |
| `extension/src/sidebar/pages/History.tsx` | Absorbed into TrackPage (keep as component) |
| `extension/src/sidebar/pages/EditProfile.tsx` | Absorbed into MePage (keep as component) |
| `extension/src/sidebar/pages/Skills.tsx` | Absorbed into MePage (keep as component) |
| `extension/src/sidebar/pages/Memories.tsx` | Absorbed into MePage (keep as component) |

---

## Scoring Badge on Apply Nav Item

When a job is detected on the current Upwork tab, the "Apply" nav item shows a small green dot:
```
✍️  ●
Apply
```

The content script already sends `JOB_DATA_EXTRACTED` → sidebar listens → store has `currentJob`. Derive `hasJobDetected = !!currentJob?.title` from store.

The badge on Find shows number of jobs scored since sidebar open: read from `scoredJobsCache` count in `chrome.storage.local` on mount.

---

## Execution Order

1. **AppShell + PersistentNav** — bottom nav only; routes still work as before (least risky first)
2. **Generator header simplification** — remove 5 tab nav from Generator; nav now in bottom bar
3. **MePage** — merge Profile/Skills/Memories into one Me mode page with sub-nav
4. **FindPage** — wire in ScoredJobs (from PLAN-scored-jobs-view.md Sprint C)
5. **TrackPage** — wire in Dashboard (from PLAN-pipeline-dashboard.md)
6. **Store cleanup** — remove obsolete top-level route names, update type union

---

## Visual Reference (ASCII wireframe)

```
Phase 1 (current): ───────────────────────
┌──────────────────────┐
│ UpApply      Logout  │  ← tier 1
│ Skills Memories Pipeline Stats Feedback │ ← 5 tiny tabs, tier 2
├──────────────────────┤
│                      │
│   generator content  │  ← can't reach tabs from other pages
│                      │
└──────────────────────┘

Phase 2 (new): ────────────────────────────
┌──────────────────────┐
│ UpApply    [Job] 87  │  ← simplified apply header (only in Apply mode)
├──────────────────────┤
│                      │
│   page content       │  ← scrollable, changes per mode
│                      │
│                      │
├──────────────────────┤
│  👤 Me  🔍①  ✍●  📊  │  ← always visible, 56px, shows badges
└──────────────────────┘
```

---

## Open Questions

- **Back button for deep pages**: The Profile wizard (multi-step setup) needs forward/back within Me mode. This is handled by the wizard's own internal step state — not by the global nav.
- **Feedback page**: Currently a full page. Move to a "?" icon in the Track mode footer or a small link at the bottom of the Me/Profile sub-tab. Remove as a first-class nav item.
- **Keyboard navigation**: Tab-index the 4 nav items so keyboard users can switch modes without a mouse.
- **First-run experience**: If profile is incomplete, auto-show Me mode with a banner: "Complete your profile to improve scoring accuracy." — same as current Setup flow but now discoverable from the nav.
