# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PowerNight is a Docker container application that automates Tesla Powerwall backup reserve management. It uses a **React SPA frontend** with a **Flask API backend** to provide scheduling, monitoring, and control capabilities.

**Technology Stack:**
- Backend: Python 3.10+ (Flask, SQLAlchemy, pypowerwall)
- Frontend: React 19.2 + TypeScript + Vite + Tailwind CSS + React Router 7
- Database: SQLite (file-based)
- Deployment: Docker (multi-stage build)
- Task Scheduling: Background thread with `schedule` library

## Common Commands

### Python Backend

```bash
# Install dependencies
pip install -e .                          # Development install
pip install -e ".[dev]"                   # With dev dependencies
pip install -e ".[test]"                  # With test dependencies

# Run tests
pytest tests/                             # All tests
pytest tests/unit/                        # Unit tests only
pytest tests/integration/                 # Integration tests only
pytest -v tests/unit/test_config_manager.py  # Single file
pytest tests/unit/test_scheduler.py::TestScheduleManager::test_schedule_manager_initialization -v  # Single test

# Code quality
black src/                                # Format code
isort src/                                # Sort imports
flake8 src/                               # Lint
mypy src/                                 # Type check
bandit -r src/                            # Security scan

# Coverage
pytest --cov=src/powernight --cov-report=html tests/
```

### Frontend (React)

```bash
# Install dependencies
npm install

# Development
npm run dev                               # Vite dev server (:3000)
npm run build                             # Production build → dist/
npm run preview                           # Preview production build

# Testing
npm run test                              # Unit tests (vitest)
npm run test:ui                           # Test UI
npm run test:e2e                          # E2E tests (playwright)
npm run test:e2e:ui                       # E2E test UI

# Code quality
npm run lint                              # ESLint
npm run type-check                        # TypeScript check
```

### Build Process & Version Management

**⚠️ IMPORTANT: Always use the build script for production builds!**

```bash
# Full build with version increment (RECOMMENDED)
./build.sh                                # Complete build with Docker
./build.sh --no-docker                    # Build without Docker image

# Manual build (NOT RECOMMENDED - version info won't update)
npm run build                             # Only builds frontend, no version update
```

**Build Script Features:**
- ✅ Generates fresh build timestamp
- ✅ Creates `version-info.json` with build metadata
- ✅ Copies version info to `dist/` directory
- ✅ Builds frontend with Vite
- ✅ Optionally builds Docker image with build labels

**Version Information:**
- **Build Timestamp**: Current UTC timestamp in format "YYYY-MM-DD HH:MM:SS UTC +0000"
- **Version**: Read from `pyproject.toml`
- **Dependencies**: Extracted from `package.json` and `pyproject.toml`
- **Runtime Info**: Python, Node.js, npm versions

**Files Generated:**
- `version-info.json` - Complete build metadata
- `dist/version-info.json` - Copy for web interface access

### Docker

```bash
# Build
docker build -t powernight:latest .

# IMPORTANT: Always use docker-compose for persistent data storage
# Do NOT use 'docker run' directly - it won't mount volumes!

# Docker Compose (RECOMMENDED - includes persistent volumes)
docker-compose up -d                      # Start with volumes mounted
docker-compose down                       # Stop services
docker-compose logs -f                    # View logs
docker-compose up -d --build              # Rebuild and restart

# Manual run (NOT RECOMMENDED - data will be lost on container restart)
# Only use for testing without data persistence
docker run -d -p 8020:8020 --name powernight powernight:latest
```

### Application Entry Points

```bash
# Main application (includes web interface on :8020)
python -m powernight.main

# CLI commands
powernight status                         # Get Powerwall status
powernight set-reserve 80                 # Set backup reserve to 80%
powernight test-connection                # Test Powerwall connectivity
powernight-cli --config config.yaml --verbose
```

## High-Level Architecture

### Layered Architecture

```
┌─────────────────────────────────────────┐
│  Web Layer (React SPA + Flask API)      │  Presentation & REST API
├─────────────────────────────────────────┤
│  Core Layer (Business Logic)            │  Services & Domain Logic
├─────────────────────────────────────────┤
│  Infrastructure (Persistence & Auth)    │  Database, Config, Tesla OAuth
└─────────────────────────────────────────┘
```

### Key Components and Data Flow

**1. Configuration System** (`src/powernight/core/config/`)
- **Pattern:** Singleton with thread-safe access
- **Components:** `ConfigManager` (singleton) → validation → backup/recovery
- **File Search Order:** `POWERNIGHT_CONFIG_PATH` → `./config.json` → `./config.yaml` → `./config/config.json` → `./config/config.yaml` → `~/.powernight/config.{json,yaml}`
- **Features:** Auto-backup before changes, environment variable overrides, fail-fast on missing/invalid config (no dummy-mode fallback); auto-recovery only restores a verified backup

**2. Powerwall Integration** (`src/powernight/core/powerwall/`)
- **Pattern:** Connector guarded by a circuit breaker
- **Flow:** `PowerwallConnector` → Tesla OAuth → `pypowerwall` lib → Tesla Cloud API
- **Resilience:** Circuit breaker (per site), 30s data cache TTL (serves stale cache on failure)
- **Auth:** OAuth 2.0 with PKCE, automatic token refresh

**3. Task Scheduling** (`src/powernight/core/planner/`)
- **Pattern:** Background thread with `schedule` library (lightweight, no external deps)
- **Flow:** Bootstrap from DB → Register with scheduler → 20s check loop → Execute in a background thread → Update DB
- **Models:** `Task` table with execution tracking (last_execution, last_status, execution_count), plus `TaskExecution` history and `TaskPreset` templates
- **Important:** NOT cron-based; uses Python `schedule` library for daily task execution

**4. Web Interface** (`src/powernight/web/`)
- **Backend:** Flask app factory pattern with blueprints
  - `main_blueprint`: React SPA routing (catch-all `/<path:path>`)
  - `api_blueprint` (`/api/v1/*`): Core API endpoints
  - `auth_blueprint`, `config_blueprint`, `logs_blueprint`, `tasks_blueprint`
- **Frontend:** React SPA with React Router 7
  - Routes: `/` (Dashboard), `/planner` (task management), `/history` (execution history), `/settings`
  - API Client: Axios with typed methods in `src/utils/api.ts`
  - State: React hooks + localStorage + react-hook-form (no React Query)
  - **Dashboard Page:** Displays Powerwall System Status (fetched from `/api/auth/site-details`)
    - System Information: Site Name, Site ID, Operating Mode, Battery Level
    - Power Data: Grid, Home, Battery, Solar power readings
    - Grid Settings: Backup Reserve, Grid Charging, Grid Export Mode
    - Additional Data: Load Power, Site Power, Last Updated timestamp
    - Raw Data: Collapsible JSON view of complete site details

**5. Database** (`src/powernight/core/database/`)
- **ORM:** SQLAlchemy with SQLite
- **Models:** `Task`, `TaskExecution`, `TaskPreset` (`database/models.py`). The legacy `ScheduleEntry` and `CronJob` DB models are gone (a config-schema dataclass named `ScheduleEntry` still exists in `core/config/schema.py` for `config.yaml` schedule entries)
- **Migration:** Auto-migration on startup via `migration.py` (drops the legacy `schedule_entries` table and seeds built-in task presets)
- **Sessions:** Thread-safe session management with context managers

### Flask Routing Configuration

**Critical:** Flask serves the React SPA using this routing hierarchy (order matters):

1. API routes (`/api/v1/*`) - Flask blueprints
2. Health/utility routes (`/health`, `/version`, `/favicon.ico`)
3. Assets (`/assets/*`) - React bundles from `dist/assets/`
4. Root (`/`) - Serves `dist/index.html`
5. **Catch-all (`/<path:path>`)** - Serves `dist/index.html` for React Router

**Implementation Details:**
- `app.py`: Sets `static_folder='dist'` (React build output)
- `routes.py`: Uses `send_from_directory(static_folder, 'index.html')` for SPA routes
- `api_blueprint`: Registered with `/api/v1` prefix in `app.py` before main_blueprint

### Frontend Build Process

**Vite Configuration** (`vite.config.ts`):
```typescript
{
  root: 'src/powernight/web',           // Source directory
  base: '/',                             // Base URL (assets at /assets/*)
  build: {
    outDir: '../../../dist',             // Output to project root
    rollupOptions: {
      input: 'src/powernight/web/index.html'
    }
  },
  server: {
    port: 3000,                          // Dev server
    proxy: {
      '/api': 'http://localhost:8020'    // Proxy API calls to Flask
    }
  }
}
```

**Build Output:**
- `dist/index.html` - HTML entry point
- `dist/assets/index-*.js` - React bundle (~220KB gzipped)
- `dist/assets/index-*.css` - Tailwind CSS (~24KB gzipped)

## Git Commit Policy

**IMPORTANT:**
- Do not commit changes without explicit permission from the user
- Always wait for approval before creating git commits
- Avoid including Claude-related content in commit messages

## Documentation Structure

PowerNight has multiple documentation files serving different purposes:

| File | Audience | Purpose |
|------|----------|---------|
| **CLAUDE.md** | Developers & AI Agents | Architecture, commands, development workflows (this file) |
| **AGENTS.md** | AI Agents | AI-specific instructions (web UI, Docker deployment warnings) |
| **docs/README.md** | End Users | Features, quick start, installation, usage, troubleshooting |
| **.github/workflows/README.md** | DevOps/Maintainers | CI/CD pipelines, release process, workflow documentation |

**When to use which:**
- Building/developing? → **CLAUDE.md** (common commands, architecture)
- Deploying with Docker? → **AGENTS.md** (critical volume mount warnings)
- Installing for end users? → **docs/README.md** (quick start, usage guide)
- Creating releases? → **.github/workflows/README.md** (release workflow)

## GitHub Actions & CI/CD

PowerNight uses automated GitHub Actions workflows for continuous integration and deployment:

### Available Workflows

**1. Docker Publish** (`.github/workflows/docker-publish.yml`)
- **Trigger:** Git tags matching `[0-9]+.[0-9]+.[0-9]+` (e.g., `1.0.0`)
- **Purpose:** Builds multi-architecture Docker images and publishes to:
  - GitHub Container Registry: `ghcr.io/zaai-com/powernight:<version>`
  - Docker Hub (mirror): `zaaicom/powernight:<version>`
- **Platforms:** `linux/amd64`, `linux/arm64`, `linux/arm/v7`

**2. Docker Health Test** (`.github/workflows/docker-health-test.yml`)
- **Trigger:** Pull requests and pushes to `main`
- **Purpose:** Validates Docker builds work correctly before merging

**3. Docker Security Scan** (`.github/workflows/docker-security-scan.yml`)
- **Trigger:** Manual workflow dispatch
- **Purpose:** Trivy vulnerability scanning for published images

**4. Docker Hub README Sync** (`.github/workflows/docker-hub-readme-sync.yml`)
- **Trigger:** Changes to `docs/README.md`
- **Purpose:** Keeps Docker Hub description synchronized

**5. CI** (`.github/workflows/ci.yml`)
- **Trigger:** Pull requests and pushes to `main`
- **Purpose:** Runs the test/lint gate on every change:
  - **Backend:** `pip install -e ".[dev]"`, `ruff check` (syntax/undefined-name selectors), `pytest -m "not slow"` with coverage
  - **Frontend:** `npm ci`, `npm run lint`, `npm run type-check`, `npm run test:run` (vitest), `npm run build`
  - **mypy:** backend type check (informational; `continue-on-error`)

### Workflow Documentation

For detailed workflow documentation, troubleshooting, and configuration:
→ See [.github/workflows/README.md](.github/workflows/README.md)

## Release Process

Creating a new PowerNight release triggers automated multi-architecture Docker builds:

### Steps to Create a Release

1. **Update Version** in `pyproject.toml`:
   ```toml
   version = "0.4.0"
   ```

2. **Commit Changes:**
   ```bash
   git add pyproject.toml
   git commit -m "Bump version to 0.4.0"
   git push origin main
   ```

3. **Create and Push Tag:**
   ```bash
   git tag -a 0.4.0 -m "Release 0.4.0 - Description of changes"
   git push origin 0.4.0
   ```

4. **Automated Build:** GitHub Actions automatically:
   - Builds multi-arch images (amd64, arm64, arm/v7)
   - Publishes to GHCR and Docker Hub
   - Updates `latest` tag
   - Typical build time: 15-20 minutes

5. **Verify Publication:**
   - **GHCR:** https://github.com/ZAAI-com/PowerNight/pkgs/container/powernight
   - **Docker Hub:** https://hub.docker.com/r/zaaicom/powernight

### Version Tagging Convention

PowerNight follows semantic versioning (MAJOR.MINOR.PATCH):
- **MAJOR** - Breaking changes (e.g., 1.0.0 → 2.0.0)
- **MINOR** - New features (e.g., 1.0.0 → 1.1.0)
- **PATCH** - Bug fixes (e.g., 1.0.0 → 1.0.1)

**Important:** Only tags matching the pattern `[0-9]+.[0-9]+.[0-9]+` trigger the publish workflow.

For detailed release procedures and troubleshooting:
→ See [.github/workflows/README.md](.github/workflows/README.md#release-process)

## Critical Architecture Decisions

### 1. NEVER Recreate Vanilla JS Implementation

**Historical Context:** The project previously had duplicate implementations:
- Vanilla JS/HTML/CSS in `static/js/`, `templates/`, `static/css/` (removed: 12,993 lines)
- React SPA in `src/powernight/web/src/` (current implementation)

**Current State:**
- ✅ **ONLY** React SPA exists (`src/powernight/web/src/`)
- ❌ DO NOT recreate vanilla JS files
- ❌ DO NOT recreate Jinja2 templates
- ❌ DO NOT recreate custom CSS files

**Rationale:** Complete duplication was removed to maintain single source of truth.

### 2. Configuration Loading (Fail-Fast)

Configuration loading fails closed. There is NO dummy-mode fallback anymore (that code was deleted):
1. Load the user config using the search order above
2. If the file is missing, unparseable, or fails validation → raise `ConfigurationError` and refuse to start
3. Auto-recovery (`ConfigRecoveryManager`) only ever restores from a verified backup; it never fabricates a default config over the user's file
4. `create_default_config()` is used only by the explicit `create-config` CLI command, never on the load path

**Environment Variable Overrides**

`ConfigManager._apply_env_overrides` maps 12 environment variables onto config sections:
- `POWERNIGHT_LOG_LEVEL` → `logging.level`
- `POWERNIGHT_WEB_PORT`, `POWERNIGHT_WEB_HOST`, `POWERNIGHT_WEB_DEBUG` → `web_interface.*`
- `POWERNIGHT_AUTH_ENABLED`, `POWERNIGHT_API_KEY` → `web_interface.*`
- `TESLA_EMAIL` and `POWERNIGHT_POWERWALL_EMAIL` → `powerwall.tesla_email`
- `POWERNIGHT_POWERWALL_TIMEOUT` → `powerwall.timeout`
- `POWERNIGHT_AUTOMATION_ENABLED`, `POWERNIGHT_AUTOMATION_INTERVAL` → `automation.*`
- `POWERNIGHT_MONITORING_ENABLED` → `monitoring.enabled`

Four more environment variables are read outside that map: `POWERNIGHT_CONFIG_PATH` (config search), `POWERNIGHT_DATA_PATH` (data/token/secret location), `POWERNIGHT_STATIC_PATH` (React build dir), and `FLASK_SECRET_KEY` (session secret).

### 3. Resilience Patterns

**Circuit Breaker** (`scheduler/circuit_breaker.py`):
- States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing recovery)
- Prevents cascading failures when Tesla API is unreliable
- Configurable failure threshold and recovery timeout

**Retry Settings:**
- The Powerwall connector exposes `retry_attempts` / `retry_delay` / `max_retry_delay` config knobs.
- The former `tenacity`-based `@retry` decorator has been removed (tenacity is no longer a dependency); resilience is provided by the circuit breaker and the stale-cache fallback rather than an automatic retry loop.

**Data Caching:**
- Powerwall data cached for 30s TTL
- Reduces API calls and improves responsiveness

### 4. Task Execution Model

**Important:** PowerNight uses the Python `schedule` library, NOT traditional cron:
- Tasks execute once daily at specified time (HH:MM format)
- Background thread checks every 20 seconds (`planner.py`, `_check_interval = 20.0`)
- Each due task runs in its own background thread, so execution never blocks the check loop
- Execution tracked in the `Task` table (last_execution, execution_count), with a per-run row in `TaskExecution`
- Tasks loaded from database on startup ("bootstrapping")

**Why Not Cron:**
- Simplicity: No external dependencies
- Portability: Works in Docker without cron daemon
- Flexibility: Programmatic control over scheduling

## Code Organization Patterns

### Singleton Pattern (Thread-Safe)

```python
class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

**Used in:** `ConfigManager`, `Planner` (scheduler singleton)

### App Factory Pattern

```python
def create_app(config: Config, testing=False,
               powerwall_connector=None) -> Flask:
    app = Flask(__name__, static_folder='dist')
    configure_middleware(app)
    register_blueprints(app)  # Order matters!
    return app
```

**Blueprint Registration Order:**
1. `api_blueprint` (with `/api/v1` prefix)
2. Other API blueprints (auth, config, logs, tasks)
3. **`main_blueprint` LAST** (contains catch-all route)

### Database Session Management

```python
# Services manage their own thread-safe session context internally
task_service = TaskService()
tasks = task_service.list_tasks(enabled_only=True)

# Or open a session context directly when needed
with get_db_session_context() as session:
    ...
```

## Testing Architecture

**Test Organization:**
```
tests/
├── unit/              # Isolated component tests
├── integration/       # Multi-component interaction tests
├── web/              # Frontend tests
└── conftest.py       # Shared fixtures
```

**Pytest Markers:**
- `@pytest.mark.unit` - Fast isolated tests
- `@pytest.mark.integration` - Database/API tests
- `@pytest.mark.slow` - Long-running tests

**Key Fixtures** (`conftest.py`):
- `temp_dir` - Temporary directory for test files
- `config_file` - Temporary config with test data
- `mock_powerwall_connector` - Mocked Powerwall API

**Frontend Testing:**
- Unit: Vitest + React Testing Library
- E2E: Playwright (browser automation)

## Application Startup Flow

```
main() [src/powernight/main.py]
├─ setup_logging()
├─ if CLI args → cli()
└─ else → PowerNightApp().run()  [src/powernight/app.py]
   ├─ initialize()
   │  ├─ load_config() [ConfigManager.load_config(), fail-fast]
   │  ├─ apply configured log level
   │  ├─ fail-closed auth check (if explicitly enabled, require an API key or complete Basic credentials)
   │  ├─ db_migration.upgrade() [migration.py auto-migration]
   │  └─ initialize_powerwall_connector() [+ connect attempt]
   ├─ start_planner() [Planner.start(), bootstraps tasks from DB]
   ├─ start_web_interface() [create_app() factory; Flask runs in a daemon thread]
   └─ main-thread sleep loop until shutdown (Flask does NOT block the main thread)
```

## Configuration Structure

PowerNight uses a YAML-based configuration system with the following sections:

### Configuration Sections

**automation** - Task scheduling and automation:
- `enabled` (bool) - Enable/disable automation
- `schedule` (list) - Schedule entries for reserve changes
- `timezone` (str) - Timezone for scheduling (e.g., "America/Los_Angeles")
- `check_interval` (float) - Check interval in seconds

**powerwall** - Tesla Powerwall connection:
- `tesla_email` (str) - **Required** - Tesla account email
- `powerwall_id` (str) - Powerwall site ID (optional, auto-detected)
- `timeout` (float) - API timeout in seconds
- `retry_attempts` (int) - Number of retry attempts
- `verify_ssl` (bool) - Verify SSL certificates

**web_interface** - Web server settings:
- `enabled` (bool) - Enable/disable web interface
- `host` (str) - Host to bind to (default: 0.0.0.0)
- `port` (int) - Port to listen on (default: 8020)
- `debug` (bool) - Flask debug mode
- `auth_enabled` (bool) - Explicitly require authentication; defaults to false, while configured credentials automatically enable it
- `auth_required` (bool) - Require authentication (backward compatibility)
- `username` (str) - Basic auth username
- `password` (str) - Basic auth password
- `api_key` (str) - API key for authentication (X-API-Key header or Bearer token)

**logging** - Logging configuration:
- `level` (str) - Log level (DEBUG, INFO, WARNING, ERROR)
- `file_path` (str) - Log file path
- `file_enabled` (bool) - Enable/disable file logging
- `max_file_size` (str) - Maximum log file size (e.g., "10MB")
- `backup_count` (int) - Number of backup log files
- `console_output` (bool) - Enable/disable console logging
- `format` (str) - Log format string

**monitoring** - Monitoring and health checks:
- `enabled` (bool) - Enable/disable monitoring
- `health_check_interval` (float) - Health check interval in seconds
- `circuit_breaker_enabled` (bool) - Enable/disable circuit breaker
- `circuit_breaker_failure_threshold` (int) - Failure threshold
- `circuit_breaker_recovery_timeout` (float) - Recovery timeout in seconds
- `data_cache_ttl` (float) - Data cache TTL in seconds

### Configuration Notes

- All configuration fields are defined in `src/powernight/core/config/schema.py`
- Configuration validation happens on load via dataclass validators
- Environment variable overrides are supported (see below)
- Missing optional fields use schema defaults

## Common Development Scenarios

### Adding a New API Endpoint

1. Add endpoint to appropriate blueprint in `src/powernight/web/api/`
2. Add TypeScript client method to `src/powernight/web/src/utils/api.ts`
3. Add unit test in `tests/web/test_web_api.py`
4. Use in React component via `useApi()` hook
5. Rebuild: `./build.sh --no-docker` (recommended) or `npm run build`

### Adding a New React Page

1. Create component in `src/powernight/web/src/pages/NewPage.tsx`
2. Add route in `src/powernight/web/src/App.tsx`
3. Add navigation link in `Header.tsx`
4. Build: `./build.sh --no-docker` (recommended) or `npm run build`
5. Test: Access via Flask at `http://localhost:8020/new-page`

### Adding a New Configuration Option

1. Add field to dataclass in `src/powernight/core/config/schema.py`
2. Add validation in `validators.py`
3. Add default value in dataclass definition
4. Update tests in `tests/unit/test_config_manager.py`
5. Document environment variable override (if needed)

### Debugging Powerwall Connection Issues

1. Check logs: `docker logs powernight` or application console
2. Verify OAuth tokens: Check the data directory (`/data`) for `.pypowerwall.auth` and `.pypowerwall.site`
3. Test connection: `powernight test-connection`
4. Check circuit breaker state: Monitor `/api/v1/health` endpoint
5. Enable debug mode: Set `POWERNIGHT_LOG_LEVEL=DEBUG`

### Web Interface Troubleshooting

**Issue: 404 on React routes after deployment**
- **Cause:** Flask catch-all route not configured correctly
- **Solution:** Ensure `routes.py` has `/<path:path>` route serving `index.html`
- **Verify:** Check blueprint registration order - `main_blueprint` must be registered LAST

**Issue: Assets not loading (blank page or missing styles)**
- **Cause:** Incorrect static folder path in Flask configuration
- **Solution:** Verify `app.py` sets `static_folder='dist'`
- **Verify:** Check `dist/assets/` directory exists after build
- **Build:** Run `./build.sh --no-docker` to regenerate assets

**Issue: API calls failing from React (CORS errors)**
- **Cause:** API blueprint not registered with correct prefix
- **Solution:** Check `api_blueprint` registered with `/api/v1` prefix in `app.py`
- **Verify:** API blueprint must be registered BEFORE `main_blueprint`
- **Test:** `curl http://localhost:8020/api/v1/status` should return JSON

**Issue: Old vanilla JS code references or imports**
- **Cause:** Stale imports or documentation from legacy implementation
- **Solution:** Remove all references to `static/js/`, `templates/`, `static/css/`
- **Remember:** Only React SPA exists - no vanilla JS/Jinja2/custom CSS

**Note:** For detailed web UI architecture and AI-specific guidance, see [AGENTS.md](AGENTS.md).

## Docker Deployment

**Multi-Stage Build:**
1. **Builder stage:** Install Python dependencies in virtual environment
2. **Production stage:** Copy venv, create non-root user, setup directories

**Runtime Configuration:**
- User: `powernight:powernight` (non-root)
- Port: 8020 (internal), map to any external port
- Volumes: `/data` (persistent database and auth tokens)
- Health check: `curl http://localhost:8020/health` (every 30s)

**Environment Variables:** Pass via docker-compose.yml or `-e` flags

### Critical: Data Persistence & Volume Mounts

**⚠️ ALWAYS use docker-compose for production deployment!**

**Why docker-compose is required:**
- `docker run` does NOT mount volumes by default → data loss on container restart
- `docker-compose.yml` configures persistent volume for `/data`
- All critical data (SQLite DB, OAuth tokens) stored in `/data`

**Data Storage Structure:**
```
Host: ./PowerNight-Data/          Container: /data/
├── powernight.db                 SQLite database (tasks, executions, presets)
├── .pypowerwall.auth             Tesla OAuth tokens (plain JSON, mode 0o600)
├── .pypowerwall.site             Selected Powerwall site ID
├── .flask_secret                 Persisted Flask session secret (mode 0o600)
├── logs/                         Application logs
└── tokens/                       Token cache directory
```

**Volume Configuration (docker-compose.yml):**
```yaml
volumes:
  - ./PowerNight-Data:/data  # Bind mount to local directory
```

**Correct Usage:**
```bash
# ✅ Correct - persistent data
docker-compose up -d

# ✅ Verify volume is mounted
docker inspect PowerNight | grep -A 5 "Mounts"

# ❌ Wrong - data lost on restart
docker run -d -p 8020:8020 powernight:latest
```

**Data Backup:**
```bash
# Backup entire data directory
tar -czf powernight-backup-$(date +%Y%m%d).tar.gz PowerNight-Data/

# Restore from backup
tar -xzf powernight-backup-20251019.tar.gz
```

## Logging Structure

**Structured Logging** (`src/powernight/utils/logging.py`):
```python
@dataclass
class LogEntry:
    timestamp: str
    component: ComponentType      # WEB, POWERWALL, SCHEDULER, etc.
    operation: OperationType      # STARTUP, CONFIG_LOAD, etc.
    level: LogLevel              # DEBUG, INFO, WARNING, ERROR
    message: str
    duration_ms: Optional[float]
    metadata: Optional[Dict]
```

**Log Levels:**
- DEBUG: Detailed diagnostics
- INFO: Normal operations (default)
- WARNING: Potential issues
- ERROR: Operation failures
- CRITICAL: System failures

**Log Output:**
- Console: Real-time output
- File: Rotating file handler (configured in logging settings)
- Format: Structured JSON or human-readable

## Security Considerations

**Tesla OAuth 2.0:**
- PKCE (Proof Key for Code Exchange) for enhanced security
- Tokens stored as plain JSON in `.pypowerwall.auth` (teslapy cache format). They are NOT encrypted at rest: `pypowerwall`/`teslapy` read and rewrite this file directly, so encrypting it would break the Tesla cloud connection. It is protected with owner-only permissions instead (auth/site files `0o600`, data directory `0o700`)
- Automatic token refresh before expiration

**Web/API Authentication (optional for trusted LANs):**
- `web_interface.auth_enabled` defaults to `False`; a nonempty API key or complete username/password pair automatically enables authentication
- Explicitly enabling authentication without a usable credential still refuses startup (fail closed)
- Credentials accepted via `X-API-Key` header or `Authorization: Bearer <key>`
- When authentication is enabled, sensitive endpoints require it (`/api/v1/status`, tasks, `logs/executions`, all `/api/auth/tesla/*`, `site-details`, `tesla/info`, `POST config/timezone`); only `/health` and `/version` stay public
- Security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`) and rate limiting on auth/setup endpoints are applied in `web/middleware.py`
- Flask `SECRET_KEY` comes from `FLASK_SECRET_KEY` or is persisted under the data path (`.flask_secret`, mode `0o600`) so sessions survive restarts
- `docker-compose.yml` accepts an optional `POWERNIGHT_API_KEY`; omit it for a trusted-LAN deployment or set it to enable protection automatically

**Docker Security:**
- Non-root user (`powernight:powernight`)
- `no-new-privileges` enabled in `docker-compose.yml`; `/data` is the only writable volume
- No unnecessary capabilities

**Environment Variables:**
- Never commit secrets to git
- Use `.env` file for local development (git-ignored)
- Docker secrets for production

## Performance Characteristics

**Task Scheduling:**
- Check interval: 20 seconds
- Execution: Once daily per task at specified time
- Overhead: Minimal (background thread, <1% CPU)

**Powerwall API Caching:**
- TTL: 30 seconds
- Reduces API calls by ~98%
- Improves response time from ~2s to ~10ms

**Database:**
- SQLite (file-based, single-writer)
- Connection pooling via SQLAlchemy
- Adequate for single-instance deployment

**Frontend Bundle Size:**
- JavaScript: ~220KB gzipped
- CSS: ~24KB gzipped
- Initial load: <500ms on broadband

## Known Limitations

1. **Single Powerwall Site:** Currently supports one Powerwall site per instance
2. **SQLite Concurrency:** Single-writer limitation (adequate for use case)
3. **No User Management:** Single-tenant application (one user per instance)
4. **Time Zone:** Uses system timezone for scheduling (configure via environment or config)
5. **Tesla API Rate Limits:** Respects Tesla's rate limits with caching, connector-side rate limiting, and a circuit breaker

## Monitoring and Observability

**Health Check Endpoint:** `GET /health` (public; `GET /version` is also public)
```json
{
  "status": "healthy",
  "timestamp": "2026-01-01T10:00:00Z",
  "version": "2.0.0"
}
```
(`version` is read from `__version__`, currently `2.0.0`. `/health` returns `503` with `status: "unhealthy"` on error.)

**Status Endpoint:** `GET /api/v1/status` (requires auth)
- Comprehensive system status
- Powerwall connection state
- Scheduler state (job count, next run)
- Configuration state

**Execution Log API:** `GET /api/v1/logs/executions` (requires auth)
- Returns task execution history (there is no `/api/logs` endpoint)
- Filters: `limit`, `offset`, `status`, `task_name`, `execution_type`, `start_date`, `end_date`
