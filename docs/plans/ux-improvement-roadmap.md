# PowerNight UX Improvement Roadmap

## Status Update

**Phase 1 (Quick Wins) is now IMPLEMENTED:**
- 1.1 `ConfirmDialog` is wired into the Planner page (replacing native `confirm()`/`alert()`).
- 1.2 A toast notification system exists (`contexts/ToastContext.tsx`) and is used across pages.
- 1.3 A system health indicator is in the `Header`, polling `/api/v1/health` every 30s (the originally-planned `/health/detailed` endpoint no longer exists, so this was implemented against `/api/v1/health`).
- 1.4 Dashboard refreshes every 20 seconds with no interval dropdown and pauses while hidden.
- 1.5 History page supports server-side filtering (status and task name) via `GET /api/v1/logs/executions`.

**Descoped / needs new backend** (the endpoints these items assumed have since been removed from the API):
- 2.4 Circuit breaker & diagnostics panel: `/circuit-breakers`, `/health/detailed`, `/degradation` are gone. Needs a new backend endpoint.
- 5.2 Notification configuration UI: the `/notifications/*` API was removed. Needs a new backend.
- 5.4 Configuration history & rollback: `/config/history` and `/config/rollback` were removed. Needs a new backend.
- 2.3 Next scheduled task widget relied on `/schedules/next-execution`, which was also removed; it would need a new endpoint (planner does expose a `next_run` via `/api/v1/status`).

Items still valid as written include 3.1 (per-task sparkline uses the still-present `GET /api/v1/tasks/<id>/executions`) and the purely-frontend polish in Phases 3-5.

---

## Current baseline

Phase 1 is complete: Planner uses ConfirmDialog and toasts, Header uses authenticated
serial health polling, Dashboard refresh runs every 20 seconds and pauses
while hidden, and History filters status immediately while debouncing task names.
Requests do not overlap; manual Dashboard refresh remains available.

The following phases are future proposals, not claims about existing endpoints.
Removed endpoints must not be wired up without a separately approved backend.

---

## Phase 2: Dashboard & Monitoring (High Impact, Medium Effort)

### 2.1 Battery level gauge visualization
- **Why:** A percentage number is easy to miss; a visual gauge with color coding is immediately understood
- **How:** SVG-based circular or linear gauge. Color: green (>50%), yellow (20-50%), red (<20%).
- **Files:** New `BatteryGauge.tsx` component, update `Dashboard.tsx`
- **Effort:** ~2-3 hours

### 2.2 Power flow diagram
- **Why:** Core value prop - users want to see energy flowing between Solar, Battery, Home, Grid at a glance
- **How:** SVG diagram with animated flow lines. Direction and thickness based on power values. Show wattage labels.
- **Files:** New `PowerFlow.tsx` component, update `Dashboard.tsx`
- **Effort:** ~4-6 hours

### 2.3 Next scheduled task widget — DESCOPED

`/schedules/next-execution` was removed. Any future widget must use the retained
`next_run` in `/api/v1/status` or define a new backend contract first.

### 2.4 Circuit breaker & diagnostics panel
> DESCOPED: the `/circuit-breakers`, `/health/detailed`, and `/degradation` endpoints were removed. Needs a new backend before this can be built.
- **Why:** When things go wrong, users need to understand why - backend tracks all this but frontend hides it
- **How:** Expandable panel on Dashboard or Settings showing circuit breaker state, failure rates, cache stats, last communication time.
- **Files:** New `Diagnostics.tsx` component, update `api.ts`
- **Effort:** ~3-4 hours

---

## Phase 3: Task Management Enhancements (Medium Impact, Medium Effort)

### 3.1 Per-task execution sparkline
- **Why:** See at a glance if a task has been succeeding or failing recently
- **How:** Tiny inline chart (last 10 executions as green/red dots) in the task table. Uses `/tasks/<id>/executions`.
- **Files:** New `Sparkline.tsx` component, update `Planner.tsx`, `api.ts`
- **Effort:** ~3-4 hours

### 3.2 Task timeline view
- **Why:** A table of times is hard to mentally map; a visual timeline shows the full day's schedule
- **How:** 24-hour horizontal timeline with task blocks positioned at their scheduled times. Toggle between table and timeline view.
- **Files:** New `TaskTimeline.tsx` component, update `Planner.tsx`
- **Effort:** ~4-6 hours

### 3.3 Execution analytics on History page
- **Why:** Users want trends - is the system getting more reliable or less?
- **How:** Summary cards at top of History page: total executions, success rate %, tasks run today. Optional: simple bar chart of daily success/failure counts.
- **Files:** Update `History.tsx`, possibly `api.ts` for aggregated data
- **Effort:** ~3-4 hours

### 3.4 Task cloning
- **Why:** Creating similar tasks from scratch is tedious
- **How:** "Clone" button on each task that pre-fills the form with that task's values (with modified name).
- **Files:** Update `Planner.tsx`
- **Effort:** ~1 hour

---

## Phase 4: Visual Polish & Dark Mode (Medium Impact, Higher Effort)

### 4.1 Dark mode
- **Why:** App is literally called "PowerNight" - dark mode is thematically perfect and reduces eye strain
- **How:** Tailwind `dark:` variant classes. Toggle in header. Persist preference in localStorage. Use CSS custom properties for theme colors.
- **Files:** `tailwind.config.js`, all page/component files, `Header.tsx` (toggle), `index.html` (class on html element)
- **Effort:** ~6-8 hours (touches many files)

### 4.2 Skeleton loading states
- **Why:** Spinners feel slower than skeleton placeholders; skeletons show layout structure while loading
- **How:** Replace `LoadingSpinner` usage on pages with skeleton components that match the page layout.
- **Files:** New `Skeleton.tsx` component, update `Dashboard.tsx`, `Planner.tsx`, `History.tsx`
- **Effort:** ~3-4 hours

### 4.3 Searchable timezone picker
- **Why:** Current dropdown has hundreds of entries with no way to search
- **How:** Replace `<select>` with a combobox/autocomplete input that filters as you type.
- **Files:** Update `Settings.tsx` or new `TimezoneSelect.tsx` component
- **Effort:** ~2 hours

### 4.4 Keyboard shortcuts
- **Why:** Power users want fast navigation and actions
- **How:** `R` to refresh, `1-4` for page navigation, `N` for new task, `?` for shortcut help overlay.
- **Files:** New `useKeyboardShortcuts` hook, `App.tsx`
- **Effort:** ~2-3 hours

---

## Phase 5: Onboarding & Advanced Features (Lower Priority)

### 5.1 First-time onboarding flow
- **Why:** New users land on an empty dashboard with no guidance
- **How:** Detect first visit (no Tesla connection). Show step-by-step guide: Connect Tesla → Create first task → See it run.
- **Files:** New `Onboarding.tsx` component, update `App.tsx`
- **Effort:** ~4-6 hours

### 5.2 Notification configuration UI
> DESCOPED: the `/notifications/*` API was removed. Needs a new backend before this can be built.
- **Why:** Notification settings would be useful if a replacement backend is approved
- **How:** Settings section for notification preferences, test button, delivery history.
- **Files:** New settings section, `api.ts` updates
- **Effort:** ~4-6 hours

### 5.3 Multi-Powerwall site selector
- **Why:** Users with multiple sites can't switch between them
- **How:** Dropdown in header or settings using `/tesla/powerwalls` endpoint.
- **Files:** Update `Header.tsx` or `Settings.tsx`, `api.ts`
- **Effort:** ~3-4 hours

### 5.4 Configuration history & rollback
> DESCOPED: the `/config/history` and `/config/rollback` endpoints were removed. Needs a new backend before this can be built.
- **Why:** A rollback UI would require a replacement backend contract
- **How:** Settings page section showing change history with rollback buttons.
- **Files:** New settings section, `api.ts` updates
- **Effort:** ~3-4 hours

---

## Critical Files Referenced

Existing files that will be modified or whose patterns will be reused:
- `src/powernight/web/src/App.tsx`: routing, lazy loading
- `src/powernight/web/src/components/Header.tsx`: navigation, place for health indicator + dark mode toggle
- `src/powernight/web/src/components/ConfirmDialog.tsx`: already used by Planner; reuse for additional confirmations
- `src/powernight/web/src/components/StatusBadge.tsx`, `LoadingSpinner.tsx`, `Tooltip.tsx`, `ErrorBoundary.tsx`: reuse
- `src/powernight/web/src/components/LogsTable.tsx`: extend for filters
- `src/powernight/web/src/pages/Dashboard.tsx`: existing auto-refresh; future gauge/power flow
- `src/powernight/web/src/pages/Planner.tsx`: existing custom dialogs; future sparkline/timeline/cloning
- `src/powernight/web/src/pages/History.tsx`: existing filters; future analytics summary
- `src/powernight/web/src/pages/Settings.tsx`: searchable timezone, token refresh, config history
- `src/powernight/web/src/utils/api.ts`: add typed methods for unused endpoints
- `src/powernight/web/src/hooks/useAuth.ts`: pattern for new hooks
- `tailwind.config.js`: enable dark mode

Retained endpoint for future per-task visualizations:
- `GET /api/v1/tasks/<id>/executions`

Tesla management uses the existing `/api/auth/tesla/*` family. Removed health,
schedule, diagnostics, notification and config-history routes are not available;
see the DESCOPED items above.

## Verification

After implementing each phase:
1. Build: `./build.sh --no-docker` (uses build script per CLAUDE.md guidance, not bare `npm run build`)
2. Lint & types: `npm run lint && npm run type-check`
3. Unit tests: `npm run test`
4. Manual smoke test: `python -m powernight.main`, open http://localhost:8020, exercise the changed pages
5. Mobile viewport check via Chrome DevTools responsive mode
6. For dark mode: toggle and verify every page has acceptable contrast in both themes
7. For real-time/polling features: verify network tab shows expected request cadence and no runaway loops

---

## Summary

| Phase | Items | Estimated Effort | Impact |
|-------|-------|-----------------|--------|
| 1 - Quick Wins | Complete | — | Implemented |
| 2 - Dashboard | 4 items | ~10-15 hours | High (core value prop) |
| 3 - Task Mgmt | 4 items | ~11-15 hours | Medium-High |
| 4 - Visual Polish | 4 items | ~13-17 hours | Medium (perception of quality) |
| 5 - Advanced | 4 items | ~14-20 hours | Medium-Low (nice to have) |

**Recommended starting point:** Reassess the unimplemented proposals against the retained API before starting Phase 2.
