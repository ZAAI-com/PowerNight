# PowerNight UX Improvement Roadmap

## Context

PowerNight's React frontend is functional but basic. Exploration of the codebase revealed that the backend exposes ~60+ API endpoints across 5 blueprints, but the frontend uses only ~25-40% of them. Many high-impact UX improvements are simply "wire up endpoints that already exist" rather than new backend work.

Notable findings driving this plan:
- A `ConfirmDialog` component already exists at `src/powernight/web/src/components/ConfirmDialog.tsx` but is unused — Planner uses native `confirm()`/`alert()` instead.
- `/health/detailed`, `/schedules/next-execution`, `/tasks/<id>/executions`, `/circuit-breakers`, `/notifications/*`, `/config/history` are all implemented but never called.
- Dashboard requires a manual "Update Data" click — no auto-refresh.
- History page has no filtering despite the backend supporting filters by status, execution_type, date range, task_name, and pagination.
- App is named "PowerNight" but has no dark mode.

The goal is to lift the perceived quality and depth of PowerNight's UI by exposing existing backend capability and polishing high-touch interactions.

---

## Phase 1: Quick Wins (High Impact, Low Effort)

These leverage existing backend APIs and unused frontend components.

### 1.1 Replace browser `alert()`/`confirm()` with custom dialogs
- **Why:** Browser dialogs are jarring, block the thread, and look unprofessional
- **How:** A `ConfirmDialog` component already exists at `src/powernight/web/src/components/ConfirmDialog.tsx` but is **unused**. Wire it into the Planner page for delete/execute confirmations.
- **Files:** `src/powernight/web/src/pages/Planner.tsx`
- **Effort:** ~30 min

### 1.2 Add toast notification system
- **Why:** Success/error feedback currently uses inline banners or browser alerts
- **How:** Add a lightweight toast component (or use `react-hot-toast`). Replace inline success messages and alerts with toasts.
- **Files:** New `Toast.tsx` component, update `Planner.tsx`, `Settings.tsx`
- **Effort:** ~1-2 hours

### 1.3 System health indicator in header
- **Why:** Users have no at-a-glance system status; backend `/health/detailed` is unused
- **How:** Add a colored dot (green/yellow/red) in the Header that polls `/health/detailed` every 30s. Click to expand details.
- **Files:** `src/powernight/web/src/components/Header.tsx`, `src/powernight/web/src/utils/api.ts`
- **Effort:** ~1 hour

### 1.4 Auto-refresh Dashboard data
- **Why:** Dashboard requires manual "Update Data" click; stale data is confusing
- **How:** Add auto-refresh with configurable interval (off/10s/30s/60s). Show countdown to next refresh. Persist preference in localStorage.
- **Files:** `src/powernight/web/src/pages/Dashboard.tsx`
- **Effort:** ~1-2 hours

### 1.5 Add log filtering to History page
- **Why:** Backend already supports status, date range, task name, and execution type filters - frontend exposes none
- **How:** Add filter bar above the logs table with dropdowns for status, execution type, and date range picker.
- **Files:** `src/powernight/web/src/pages/History.tsx`
- **Effort:** ~2-3 hours

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

### 2.3 Next scheduled task widget
- **Why:** Users want to know "when will something happen next?" without navigating to Planner
- **How:** Dashboard card showing next task name, time, and countdown. Uses `/schedules/next-execution`.
- **Files:** New `NextTask.tsx` component, update `Dashboard.tsx`, `api.ts`
- **Effort:** ~1-2 hours

### 2.4 Circuit breaker & diagnostics panel
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
- **Why:** Backend has full notification API (config, test, statistics) - none exposed
- **How:** Settings section for notification preferences, test button, delivery history.
- **Files:** New settings section, `api.ts` updates
- **Effort:** ~4-6 hours

### 5.3 Multi-Powerwall site selector
- **Why:** Users with multiple sites can't switch between them
- **How:** Dropdown in header or settings using `/tesla/powerwalls` endpoint.
- **Files:** Update `Header.tsx` or `Settings.tsx`, `api.ts`
- **Effort:** ~3-4 hours

### 5.4 Configuration history & rollback
- **Why:** Backend supports config versioning but no UI exists
- **How:** Settings page section showing change history with rollback buttons.
- **Files:** New settings section, `api.ts` updates
- **Effort:** ~3-4 hours

---

## Critical Files Referenced

Existing files that will be modified or whose patterns will be reused:
- `src/powernight/web/src/App.tsx` — routing, lazy loading
- `src/powernight/web/src/components/Header.tsx` — navigation, place for health indicator + dark mode toggle
- `src/powernight/web/src/components/ConfirmDialog.tsx` — already built, currently unused; wire into Planner
- `src/powernight/web/src/components/StatusBadge.tsx`, `LoadingSpinner.tsx`, `Tooltip.tsx`, `ErrorBoundary.tsx` — reuse
- `src/powernight/web/src/components/LogsTable.tsx` — extend for filters
- `src/powernight/web/src/pages/Dashboard.tsx` — auto-refresh, gauge, power flow, next task widget
- `src/powernight/web/src/pages/Planner.tsx` — replace alert/confirm, add sparkline, timeline view, clone button
- `src/powernight/web/src/pages/History.tsx` — add filtering UI, analytics summary
- `src/powernight/web/src/pages/Settings.tsx` — searchable timezone, token refresh, config history
- `src/powernight/web/src/utils/api.ts` — add typed methods for unused endpoints
- `src/powernight/web/src/hooks/useAuth.ts` — pattern for new hooks
- `tailwind.config.js` — enable dark mode

Backend endpoints to newly consume:
- `/api/v1/health/detailed`
- `/api/v1/schedules/next-execution`
- `/api/v1/tasks/<id>/executions`
- `/api/v1/circuit-breakers`
- `/api/v1/tesla/refresh`, `/api/v1/tesla/logout`
- `/api/v1/config/history`, `/api/v1/config/rollback`
- `/api/v1/notifications/*`

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
| 1 - Quick Wins | 5 items | ~6-9 hours | High (immediate UX quality lift) |
| 2 - Dashboard | 4 items | ~10-15 hours | High (core value prop) |
| 3 - Task Mgmt | 4 items | ~11-15 hours | Medium-High |
| 4 - Visual Polish | 4 items | ~13-17 hours | Medium (perception of quality) |
| 5 - Advanced | 4 items | ~14-20 hours | Medium-Low (nice to have) |

**Recommended starting point:** Phase 1 items can each be done independently and immediately improve perceived quality.
