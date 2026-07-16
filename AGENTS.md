# AI Agent Instructions for PowerNight

This document provides specific instructions for AI agents working on the PowerNight codebase.

## Web Application Architecture

### Current Implementation
PowerNight uses a **React SPA (Single Page Application)** with a Flask backend. There is ONLY ONE frontend implementation.

**Frontend Stack:**
- React 19.2 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- React Router 7 (client-side routing)
- react-hook-form (forms); state is React hooks + localStorage (no React Query)
- Axios (API client)

**Backend Stack:**
- Flask (Python web framework)
- Serves both the React SPA and REST API endpoints

### Critical: DO NOT Recreate Vanilla JS Implementation

**IMPORTANT:** The following were permanently removed and should NEVER be recreated:
- ❌ Vanilla JavaScript files (formerly `src/powernight/web/static/js/`)
- ❌ Jinja2 templates (formerly `src/powernight/web/templates/`)
- ❌ Custom CSS files (formerly `src/powernight/web/static/css/`)

**Reason for removal:** Complete duplication with the React app. Over 12,993 lines of duplicate code were removed.

### Directory Structure

```
src/powernight/web/
├── src/                        # React source code (ONLY frontend)
│   ├── components/             # Reusable React components
│   │   ├── ErrorBoundary.tsx
│   │   ├── Header.tsx
│   │   ├── LoadingSpinner.tsx
│   │   ├── StatusBadge.tsx
│   │   ├── ConfirmDialog.tsx
│   │   ├── Tooltip.tsx
│   │   └── LogsTable.tsx
│   ├── pages/                  # Page components
│   │   ├── Dashboard.tsx       # Main dashboard - Powerwall System Status
│   │   ├── Settings.tsx        # Settings page - Tesla OAuth, Auth Info, Version Info
│   │   ├── Planner.tsx           # Task management (formerly Scheduling)
│   │   ├── History.tsx         # Task execution history and logs
│   │   └── Login.tsx           # Login page
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAuth.ts         # Authentication hook
│   │   ├── useApi.ts          # API integration hook
│   │   └── useLocalStorage.ts # LocalStorage hook
│   ├── contexts/              # React contexts
│   │   ├── TimezoneContext.tsx # Timezone management context
│   │   └── ToastContext.tsx   # Toast notification context
│   ├── utils/                  # Utilities
│   │   ├── api.ts             # Axios API client with typed methods
│   │   └── helpers.ts         # Helper functions
│   ├── types/                  # TypeScript type definitions
│   │   └── index.ts
│   ├── App.tsx                # Main app component with routing
│   ├── main.tsx               # React entry point
│   └── index.css              # Tailwind CSS imports
├── api/                        # Flask API (Backend only)
│   ├── routes.py              # Main routes + SPA catch-all (main_blueprint)
│   ├── api.py                 # Main API blueprint (/api/v1/*)
│   ├── auth_api.py            # Tesla OAuth + auth endpoints (/api/auth/*)
│   ├── config_api.py          # Config endpoints (/api/v1/config/*)
│   ├── logs_api.py            # Execution log endpoint (/api/v1/logs/executions)
│   ├── tasks_api.py           # Task + preset endpoints (/api/v1/tasks/*)
│   ├── auth.py                # Authentication utilities (@require_auth)
│   ├── decorators.py          # API decorators (re-exports require_auth)
│   ├── errors.py              # Error handling
│   ├── monitoring.py          # Performance monitoring (not a blueprint)
│   ├── schemas.py             # Data schemas
│   └── validation.py          # Input validation
├── app.py                     # Flask app factory
├── middleware.py              # Flask middleware (CORS, security headers, rate limiting)
└── index.html                 # HTML entry point for Vite

dist/                           # Built React app (git-ignored)
├── index.html                 # Built HTML
└── assets/                    # Bundled JS/CSS
    ├── index-*.js
    └── index-*.css
```

### Flask Routing Logic

The Flask app serves the React SPA using this routing hierarchy:

1. **API Routes** (`/api/v1/*`) - Flask blueprints handle all API calls
2. **Health Routes** (`/health`, `/version`) - Basic system endpoints
3. **Assets** (`/assets/*`) - Serves React bundles from `dist/assets/`
4. **Root** (`/`) - Serves `dist/index.html`
5. **Catch-all** (`/<path:path>`) - Serves `dist/index.html` for React Router

**Key Implementation Details:**
- `app.py`: Configures `static_folder` to point to `dist/`
- `routes.py`: Implements SPA routing with `send_from_directory()`
- `api_blueprint`: Registered with `/api/v1` prefix in `app.py`

### Development Workflow

**Frontend Development:**
```bash
cd /path/to/PowerNight
npm run dev          # Vite dev server on :3000 with HMR
./build.sh --no-docker  # Production build with version increment (RECOMMENDED)
npm run build        # Frontend-only build (version info won't update)
npm run preview      # Preview production build
```

**Backend Development:**
```bash
python -m powernight.main        # Full app with web interface
# Or directly start web interface programmatically
```

**Full Stack:**
1. Frontend proxies API calls to `http://localhost:8020/api` (see `vite.config.ts`)
2. Backend serves React SPA from `dist/` in production

### Making Changes to the Web UI

**Adding a New React Component:**
1. Create component in `src/powernight/web/src/components/`
2. Import and use in page components
3. Rebuild: `./build.sh --no-docker` (recommended) or `npm run build`

**Adding a New Page:**
1. Create page component in `src/powernight/web/src/pages/`
2. Add route in `src/powernight/web/src/App.tsx`
3. Add navigation link in `Header.tsx` if needed
4. Rebuild: `./build.sh --no-docker` (recommended) or `npm run build`

**Current Routes:**
- `/` - Dashboard (Powerwall System Status)
- `/planner` - Task Management (formerly Scheduling)
- `/history` - Task Execution History and Logs
- `/settings` - Tesla OAuth, Auth Info, Version Info

**Adding a New API Endpoint:**
1. Add endpoint to appropriate blueprint in `src/powernight/web/api/`
2. Add TypeScript method to `src/powernight/web/src/utils/api.ts`
3. Use in React components via `useApi` hook
4. Rebuild frontend: `./build.sh --no-docker` (recommended) or `npm run build`

**Styling:**
- Use Tailwind CSS utility classes
- Global styles in `src/powernight/web/src/index.css`
- Component-specific styles use Tailwind classes inline

### Build Process

**⚠️ IMPORTANT: Always use the build script for production builds!**

**Build Script Usage:**
```bash
./build.sh                    # Complete build with Docker image
./build.sh --no-docker        # Build without Docker (recommended for development)
```

**Build Script Features:**
- ✅ Increments build number automatically
- ✅ Generates fresh build timestamp  
- ✅ Creates `version-info.json` with build metadata
- ✅ Copies version info to `dist/` directory
- ✅ Builds frontend with Vite
- ✅ Optionally builds Docker image with build labels

**Vite Configuration** (`vite.config.ts`):
```typescript
{
  root: 'src/powernight/web',     // Source root
  base: '/',                       // Base URL path
  build: {
    outDir: '../../../dist',       // Output to project root
    rollupOptions: {
      input: 'src/powernight/web/index.html'
    }
  }
}
```

**Version Information:**
- **Build Number**: Auto-incremented from `BUILD_NUMBER` file
- **Build Timestamp**: Current UTC timestamp in format "YYYY-MM-DD HH:MM:SS UTC +0000"
- **Version**: Read from `pyproject.toml`
- **Dependencies**: Extracted from `package.json` and `pyproject.toml`
- **Runtime Info**: Python, Node.js, npm versions

**Docker Build:**
- Dockerfile includes `npm run build` step
- Copies `dist/` to `/app/dist` in container
- Flask serves from `/app/dist` (via `POWERNIGHT_STATIC_PATH` env var)

### Authentication

PowerNight uses **Tesla authentication** via pypowerwall framework in cloud mode:
- Tesla tokens stored in `.pypowerwall.auth` file (plain JSON, mode `0o600`; not encrypted, because pypowerwall reads/rewrites it directly)
- Tesla login flow handled through Settings page

Separately, the `useAuth` hook manages optional app-level authentication for the PowerNight web API. With no credentials configured, authentication is off for trusted-LAN use. A nonempty API key or complete username/password pair automatically enables it. Sensitive endpoints then require an API key sent as `X-API-Key` or `Authorization: Bearer <key>`; only `/health` and `/version` are public. Explicitly enabling authentication without a usable credential fails closed at startup.

**Authentication Flow:**
1. User initiates Tesla login via Settings page
2. Redirects to tesla.com for login
3. After successful login, pypowerwall framework handles token storage
4. Tokens stored in `.pypowerwall.auth` file for future use
5. Authentication state checked on app startup

### API Client

**TypeScript API Client** (`src/utils/api.ts`):
- Axios-based
- Typed methods for all endpoints
- Automatic authentication handling
- Error handling with custom events
- Example:
  ```typescript
  import api from '@/utils/api';

  const status = await api.getStatus();
  const tasks = await api.getTasks();
  ```

### Common Issues & Solutions

**Issue: 404 on React routes after deployment**
- **Cause:** Flask catch-all route not configured
- **Solution:** Ensure `routes.py` has `/<path:path>` route serving `index.html`

**Issue: Assets not loading**
- **Cause:** Incorrect static folder path
- **Solution:** Verify `app.py` sets `static_folder` to `dist/`

**Issue: API calls failing from React**
- **Cause:** CORS or incorrect API prefix
- **Solution:** Check API blueprint registered with `/api/v1` prefix

**Issue: Old vanilla JS code references**
- **Cause:** Stale imports or documentation
- **Solution:** Remove references; use React app only

### Testing

**Frontend Tests:**
```bash
npm run test         # Vitest unit tests
npm run test:ui      # Vitest UI
npm run test:e2e     # Playwright E2E tests
npm run test:e2e:ui  # Playwright E2E test UI
npm run lint         # ESLint
npm run type-check   # TypeScript check
```

**Backend Tests:**
```bash
pytest tests/        # Python unit/integration tests
```

### Key Files Reference

| File | Purpose |
|------|---------|
| `src/powernight/web/src/App.tsx` | Main React app with routing |
| `src/powernight/web/src/utils/api.ts` | TypeScript API client |
| `src/powernight/web/api/routes.py` | Flask SPA routing |
| `src/powernight/web/api/api.py` | Main API blueprint |
| `src/powernight/web/app.py` | Flask app factory |
| `vite.config.ts` | Vite build configuration |
| `package.json` | Frontend dependencies & scripts |

## Docker Deployment & Data Persistence

### ⚠️ CRITICAL: Always Use docker-compose

**DO NOT use `docker run` for production deployments!**

**Why:**
- `docker run` does NOT mount volumes by default
- All data (SQLite DB, OAuth tokens) will be LOST on container restart
- `docker-compose.yml` is configured with proper volume mounts

### Data Storage Architecture

**Container Path:** `/data/`
**Host Path:** `./PowerNight-Data/`

**Files Stored:**
```
PowerNight-Data/
├── powernight.db           # SQLite database (schedules, tasks, config)
├── .pypowerwall.auth       # Tesla OAuth tokens (PKCE, refresh tokens)
├── .pypowerwall.site       # Selected Powerwall site ID
├── logs/                   # Application logs
└── tokens/                 # Token cache directory
```

### Correct Deployment Commands

```bash
# ✅ CORRECT - Start with persistent volumes
docker-compose up -d

# ✅ CORRECT - Rebuild and restart
docker-compose up -d --build

# ✅ CORRECT - Stop service
docker-compose down

# ✅ CORRECT - View logs
docker-compose logs -f PowerNight

# ❌ WRONG - Data will be lost on restart!
docker run -d -p 8020:8020 powernight:latest
```

### Volume Configuration

**docker-compose.yml:**
```yaml
services:
  PowerNight:
    image: zaaicom/powernight:latest
    container_name: PowerNight
    restart: unless-stopped
    ports:
      - "8020:8020"
    environment:
      # Optional on trusted LANs; a nonempty key automatically enables auth
      - POWERNIGHT_AUTH_ENABLED
      - POWERNIGHT_API_KEY
      - TESLA_CLIENT_ID=${TESLA_CLIENT_ID:-ownerapi}
      - TESLA_EMAIL=${TESLA_EMAIL:-your-email@example.com}
      - POWERNIGHT_AUTOMATION_ENABLED=${AUTOMATION_ENABLED:-true}
      - POWERNIGHT_LOG_LEVEL=${LOG_LEVEL:-INFO}
    volumes:
      - ./PowerNight-Data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8020/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Data Backup & Recovery

```bash
# Backup
tar -czf powernight-backup-$(date +%Y%m%d).tar.gz PowerNight-Data/

# Restore
tar -xzf powernight-backup-20251019.tar.gz

# Verify data exists
ls -la PowerNight-Data/
```

### Troubleshooting

**Problem:** Container running but no data directory
```bash
# Check if volume is mounted
docker inspect PowerNight | grep -A 5 "Mounts"

# Should show:
# "Source": "/path/to/PowerNight-Data"
# "Destination": "/data"
```

**Problem:** Lost Tesla OAuth tokens after restart
- **Cause:** Used `docker run` instead of `docker-compose`
- **Solution:** Always use `docker-compose up -d`
- **Recovery:** Re-authenticate via Settings page

## Current Page Structure

### Dashboard Page (`/`)
**File:** `src/powernight/web/src/pages/Dashboard.tsx`
**Purpose:** Real-time Powerwall system status display
**API Endpoint:** `GET /api/auth/site-details`

**Features:**
- System Information (Site Name, Site ID, Operating Mode, Battery Level)
- Power Data (Grid, Home, Battery, Solar power readings)
- Grid Settings (Backup Reserve, Grid Charging, Grid Export Mode)
- Additional Data (Load Power, Site Power, Last Updated timestamp)
- Raw Data (Collapsible JSON view of complete site details)
- Manual refresh button (no auto-fetch on mount)

### Planner Page (`/planner`)
**File:** `src/powernight/web/src/pages/Planner.tsx`
**Purpose:** Task management and scheduling (formerly Scheduling)
**API Endpoints:** `GET /api/v1/tasks`, `POST /api/v1/tasks`, `PUT /api/v1/tasks/{id}`, `DELETE /api/v1/tasks/{id}`

**Features:**
- Task creation and editing
- Command parameter configuration
- Task execution tracking
- Real-time status updates
- Task enable/disable functionality

### History Page (`/history`)
**File:** `src/powernight/web/src/pages/History.tsx`
**Purpose:** Task execution history and logs
**API Endpoints:** `GET /api/v1/logs/executions`

**Features:**
- Task execution history
- Execution status tracking
- Error logging and debugging
- Filtering and pagination

### Settings Page (`/settings`)
**File:** `src/powernight/web/src/pages/Settings.tsx`
**Purpose:** Tesla OAuth, authentication info, version info, timezone management
**API Endpoints:** `GET /api/auth/status`, `GET /api/config`, `GET /api/version-info`

**Features:**
- Tesla OAuth flow management
- Authentication status display
- Version information
- Timezone configuration
- Site selection for multi-site setups

### Login Page
**File:** `src/powernight/web/src/pages/Login.tsx`
**Purpose:** Tesla authentication flow
**Features:**
- Tesla login flow initiation
- Authentication state management
- Error handling for authentication failures
- Redirect to Settings page for Tesla login

## Current Component Structure

### React Components
- **ErrorBoundary.tsx** - Error boundary for React error handling
- **Header.tsx** - Navigation header with route highlighting
- **LoadingSpinner.tsx** - Loading indicator component
- **StatusBadge.tsx** - Status display component
- **ConfirmDialog.tsx** - Confirmation dialog for destructive actions
- **Tooltip.tsx** - Tooltip component for help text
- **LogsTable.tsx** - Table component for displaying execution logs

### React Hooks
- **useAuth.ts** - Authentication state management
- **useApi.ts** - API integration with loading states
- **useLocalStorage.ts** - LocalStorage persistence hook

### React Contexts
- **TimezoneContext.tsx** - Timezone management and display
- **ToastContext.tsx** - Toast notification provider used across pages

### TypeScript Types
- **AuthStatus** - Authentication state interface
- **Task** - Task management interface
- **CommandDefinition** - Command parameter definitions
- **LogEntry** - Log entry structure
- **ApiResponse** - Standardized API response format

## Summary for Agents

When working on PowerNight:

**Web UI Features:**
1. ✅ Edit React components in `src/powernight/web/src/`
2. ✅ Use TypeScript for type safety
3. ✅ Use Tailwind CSS for styling
4. ✅ Add API methods to `utils/api.ts`
5. ✅ Rebuild with `./build.sh --no-docker` (recommended) or `npm run build`
6. ❌ NEVER recreate vanilla JS/templates/CSS
7. ❌ NEVER bypass the React app

**Current Routes:**
- `/` - Dashboard (Powerwall System Status)
- `/planner` - Task Management (formerly Scheduling)
- `/history` - Task Execution History and Logs
- `/settings` - Tesla OAuth, Auth Info, Version Info

**Docker Deployment:**
1. ✅ ALWAYS use `docker-compose up -d`
2. ✅ Verify volumes are mounted
3. ✅ Backup `PowerNight-Data/` directory
4. ❌ NEVER use `docker run` for production
5. ❌ NEVER ignore volume configuration

**Data Persistence:**
- All critical data in `/data` (container) → `./PowerNight-Data/` (host)
- SQLite database, OAuth tokens, logs all require persistent storage
- Data loss occurs if container runs without volume mounts

**Authentication:**
- Tesla authentication via pypowerwall framework in cloud mode
- Authentication state managed by `useAuth` hook
- Tesla tokens stored in `.pypowerwall.auth` file
- Login flow initiated through Settings page

The React SPA is the single source of truth for the PowerNight web interface.
