# PowerNight Security Remediation Plan

## Status: IMPLEMENTED, THEN SUPERSEDED (with corrections)

This plan shipped, but its auth-on-by-default deployment policy was superseded in July 2026. Authentication is now credential-driven: no credential means open trusted-LAN access, while a configured API key or complete Basic-auth pair automatically enables protection. Explicitly enabling authentication without credentials still fails closed.

- **Auth is optional by default** (`schema.py` `WebInterfaceSettings.auth_enabled=False`), with credentials automatically opting in and an explicit misconfigured opt-in still failing closed (`app.py`).
- **Sensitive endpoints require auth** via `@require_auth` (`/api/v1/status`, all `tasks/*`, `logs/executions`, all `/api/auth/tesla/*`, `site-details`, `tesla/info`, `POST /api/v1/config/timezone`); `/health` and `/version` remain public. OAuth setup endpoints are gated by an internal `_setup_allowed()` (loopback bootstrap or authenticated).
- **Flask `SECRET_KEY`** is set from `FLASK_SECRET_KEY` or persisted to `<data>/.flask_secret` (mode `0o600`).
- **Security headers + rate limiting + restricted CORS** are applied in `web/middleware.py`; HSTS is conditional on HTTPS.
- **docker-compose accepts an optional `POWERNIGHT_API_KEY`**; setting one automatically enables authentication.

Corrections found while implementing (the plan's assumptions did not all hold):

1. **Password hashing (Phase 3.1) was dropped, not added.** `passlib` 1.7.4 is incompatible with `bcrypt` >= 4.1, so rather than hash passwords with passlib+bcrypt, `bcrypt`, `passlib`, `pyjwt`, and `authlib` were **removed** from runtime dependencies entirely. Authentication relies on the API key / password comparison with `hmac.compare_digest`.
2. **Tokens were hardened with file permissions, not Fernet (Phase 1.4).** `pypowerwall`/`teslapy` read and rewrite the `.pypowerwall.auth` file directly (the connector passes `authpath=...`), so encrypting it at rest would break the Tesla cloud connection. Instead the auth/site files are `0o600` and the data directory is `0o700`. The file stays plain JSON by necessity.
3. **The "enterprise" modules were deleted, not wired up.** The `web/api/middleware.py`, `web/api/config_manager.py`, and `web/api/docs.py` (OpenAPI) modules referenced throughout this plan no longer exist. Security headers and rate limiting now live in a new, smaller `web/middleware.py`, and there is no `/docs` OpenAPI blueprint.

The remaining sections below are the original plan as written, kept for historical context.

---

## Context

A security review of the PowerNight codebase (a Tesla Powerwall management web app exposing port 8020) surfaced **5 critical**, **3 high**, **6 medium**, and **3 low** severity findings. The most consequential issues stem from:

1. Authentication being **disabled by default** (`auth_enabled=False`), making the entire API world-readable in a default deployment.
2. **6 endpoints in the auth blueprint** that have no `@require_auth` decorator regardless of the auth setting: including OAuth setup, Tesla credential info, and live site sensor data.
3. **Tesla OAuth tokens stored in plaintext** on disk despite `cryptography` (Fernet) already being a dependency.
4. **Implemented-but-unused security middleware** (`@rate_limit`, `@secure_endpoint`, `SecurityMiddleware.add_security_headers`) that is never wired to any endpoint.

The intended outcome is a hardened default deployment that does not require user configuration to be safe, and which fails closed rather than open.

---

## Phase 1: Critical: Close the open-by-default holes

### 1.1 Default authentication ON
**File:** `src/powernight/core/config/schema.py:140-146` (`WebInterfaceSettings`)
- Change `auth_enabled: bool = False` → `auth_enabled: bool = True`
- Change `cors_origins: List[str] = ["*"]` → `["http://localhost:3000", "http://localhost:8020"]`
- Add startup-time validation: if `auth_enabled=True` and `api_key`/`password` are both `None`, refuse to start (log instructions).

**File:** `src/powernight/web/api/auth.py:17-57` (`@require_auth`)
- Keep the existing `auth_enabled=False` bypass but log a `WARNING` once at startup so disabled auth is visible in logs/health checks.

### 1.2 Add `@require_auth` to all auth-blueprint endpoints
**File:** `src/powernight/web/api/auth_api.py`
Add `@require_auth` to:
- `GET /tesla/status` (line ~33)
- `GET /tesla/info` (line ~80)
- `GET /site-details` (line ~484)
- `GET /setup/status/<session_id>` (line ~296)

For OAuth setup endpoints (`/setup/start`, `/setup/callback`, `/setup/complete`), apply this rule:
- If valid Tesla tokens already exist OR `auth_enabled=True` and the user is unauthenticated → return 401.
- Only allow first-time setup when no tokens exist AND request comes from `127.0.0.1` (loopback bootstrap), OR when authenticated.

Implement a new helper `_setup_allowed()` in `auth_api.py` and gate the three setup endpoints with it.

### 1.3 Remove `?include_sensitive=true` exposure
**File:** `src/powernight/web/api/api.py:124` and `src/powernight/web/api/config_manager.py:396-428`
- Delete the `include_sensitive` query parameter handling entirely.
- Always redact `password`, `api_key`, `tesla_email`, `powerwall_id` in `_filter_sensitive_data`.
- Fix the field-name bug: replace `email` → `tesla_email` in the redaction list so the email is actually masked.

### 1.4 Encrypt Tesla OAuth tokens at rest
**File:** `src/powernight/core/auth/token_storage.py:46-171`
- Use the already-imported `cryptography.fernet.Fernet`.
- Derive a per-machine key from a stable identifier (e.g., a `key.bin` written under `/data` on first run with `chmod 0600`).
- `store_auth_data()`: serialize JSON → `Fernet(key).encrypt(...)` → write bytes to `.pypowerwall.auth`.
- `load_auth_data()`: read bytes → `Fernet(key).decrypt(...)` → JSON parse. Provide one-shot migration: if the file parses as plain JSON, re-encrypt and overwrite.
- Tighten file mode `0o640` → `0o600`.

### 1.5 Remove default API key placeholder
**File:** `docker-compose.yml:26`
- Change `POWERNIGHT_API_KEY=${POWERNIGHT_API_KEY:-your-secure-api-key-here}` → `POWERNIGHT_API_KEY=${POWERNIGHT_API_KEY:?POWERNIGHT_API_KEY must be set}`. Compose will refuse to start without it.
- Update `docs/README.md` and `.env.example` (create if absent) to instruct users to generate a strong key.

---

## Phase 2: High: Authentication and session integrity

### 2.1 Protect logs and config-write endpoints
**File:** `src/powernight/web/api/logs_api.py:24-26`
- Remove `@cross_origin()` from `GET /api/v1/logs/executions`.
- Add `@require_auth`.
- Audit the rest of `logs_api.py` and `config_api.py` for other unprotected mutating endpoints (`POST /api/v1/config/timezone` at `config_api.py:84-118` is confirmed missing auth).

### 2.2 Set Flask `SECRET_KEY`
**File:** `src/powernight/web/app.py:52-55`
- After `app = Flask(...)`, add:
  ```python
  app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
  ```
- If env var unset, persist the generated value to `/data/.flask_secret` (mode `0o600`) so it survives restarts.

---

## Phase 3: Medium: Defense in depth

### 3.1 Hash passwords with bcrypt
**Files:** `src/powernight/core/config/schema.py:144`, `src/powernight/web/api/auth.py:143-152`
- Add a `password_hash: Optional[str]` field; deprecate `password`.
- On first config load, if `password` is set and `password_hash` is empty, hash with `bcrypt` and rewrite config; null out `password`.
- Use `passlib.hash.bcrypt.verify(submitted, stored_hash)` for comparison.

### 3.2 Constant-time comparison
**File:** `src/powernight/web/api/auth.py:192-198`
- Replace the custom `_constant_time_compare` with `hmac.compare_digest(a, b)`.

### 3.3 Restrict CORS in debug fallback
**File:** `src/powernight/web/middleware.py:11-12`
- Replace wildcard CORS with explicit allow-list `["http://localhost:3000"]`, even in debug.

### 3.4 Wire up rate limiting + security headers
**File:** `src/powernight/web/api/middleware.py` + `src/powernight/web/app.py`
- Apply `@rate_limit('auth')` to `/api/v1/auth/login`, `/setup/start`, `/setup/callback`, `/setup/complete`, `/tesla/test-connection`.
- Register `SecurityMiddleware.add_security_headers` via `app.after_request` so all responses get `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`, etc.
- Tighten the existing CSP to remove `unsafe-inline` for `script-src` (Vite emits hashed bundles, no inline scripts needed).

### 3.5 Generic error responses
**Files:** `src/powernight/web/api/auth_api.py`, `config_api.py`, `logs_api.py`, `api.py`
- Replace patterns like `return jsonify({"error": str(e)}), 500` with a helper `error_response(public_msg, exc, status)` that:
  - Logs full traceback server-side.
  - Returns `{"error": "<generic message>", "request_id": "<uuid>"}` to the client.

### 3.6 Protect config backups
**Files:** `.gitignore`, `src/powernight/web/api/config_manager.py:449-454`
- Add `.config_backups/` to `.gitignore`.
- Strip `password`, `password_hash`, `api_key`, `tesla_email`, `powerwall_id` from the dict before writing each backup.
- Set backup file mode `0o600`.

---

## Phase 4: Low: Hygiene

### 4.1 Validate `auth_url` client-side
**File:** `src/powernight/web/src/pages/Login.tsx:27-28`
- Before `window.location.href = data.auth_url`, parse with `new URL(...)` and assert `host === "auth.tesla.com"`.

### 4.2 Remove dead import
**File:** `src/powernight/web/api/docs.py:12`
- Delete the unused `render_template_string` import.

### 4.3 Make HSTS conditional
**File:** `src/powernight/web/api/middleware.py:483-484`
- Only emit `Strict-Transport-Security` when `request.is_secure` or `X-Forwarded-Proto: https`.

---

## Files to be modified (summary)

| File | Phase(s) |
|---|---|
| `src/powernight/core/config/schema.py` | 1.1, 3.1 |
| `src/powernight/web/api/auth.py` | 1.1, 3.1, 3.2 |
| `src/powernight/web/api/auth_api.py` | 1.2, 3.5 |
| `src/powernight/web/api/api.py` | 1.3, 3.5 |
| `src/powernight/web/api/config_manager.py` | 1.3, 3.6 |
| `src/powernight/web/api/config_api.py` | 2.1, 3.5 |
| `src/powernight/web/api/logs_api.py` | 2.1, 3.5 |
| `src/powernight/web/api/middleware.py` | 3.4, 4.3 |
| `src/powernight/web/api/docs.py` | 4.2 |
| `src/powernight/web/app.py` | 2.2, 3.4 |
| `src/powernight/web/middleware.py` | 3.3 |
| `src/powernight/core/auth/token_storage.py` | 1.4 |
| `src/powernight/web/src/pages/Login.tsx` | 4.1 |
| `docker-compose.yml` | 1.5 |
| `.gitignore` | 3.6 |

Existing utilities to reuse (no new code needed):
- `cryptography.fernet.Fernet`: already imported in `token_storage.py`
- `bcrypt` 4.2.1 + `passlib` 1.7.4: already in `pyproject.toml`
- `rate_limit()`, `secure_endpoint()`, `SecurityMiddleware.add_security_headers()`: already implemented in `src/powernight/web/api/middleware.py`, just unused

No new dependencies are required.

---

## Verification

After each phase, run:

1. **Static checks**
   ```
   flake8 src/
   mypy src/
   bandit -r src/
   pytest tests/
   ```

2. **Auth-on-by-default smoke test**
   ```
   POWERNIGHT_API_KEY="$(openssl rand -hex 32)" docker-compose up -d
   curl -i http://localhost:8020/api/v1/status                    # expect 401
   curl -i http://localhost:8020/api/auth/site-details            # expect 401  (Phase 1.2)
   curl -i http://localhost:8020/api/v1/logs/executions           # expect 401  (Phase 2.1)
   curl -i http://localhost:8020/api/v1/config?include_sensitive=true  # expect no password/api_key in body  (Phase 1.3)
   curl -i -H "X-API-Key: $POWERNIGHT_API_KEY" http://localhost:8020/api/v1/status  # expect 200
   ```

3. **Token encryption verification**
   - After OAuth setup, `xxd /data/.pypowerwall.auth | head` should not show readable JSON (Phase 1.4).
   - Stop and restart the container; tokens still load (decryption works).

4. **Rate limit verification**
   - Loop 20 wrong-password POSTs to `/api/v1/auth/login`: expect HTTP 429 after the threshold (Phase 3.4).

5. **Security headers**
   - `curl -I http://localhost:8020/` shows `X-Frame-Options`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy`, `Referrer-Policy` (Phase 3.4).

6. **Browser end-to-end**
   - Run `./build.sh --no-docker && python -m powernight.main`, log in via Tesla OAuth, verify dashboard loads, verify no plaintext credentials in DevTools network tab.

---

## Out of scope

- Adding multi-user / role-based access: single-tenant is by design (per CLAUDE.md "Known Limitations").
- Migrating away from SQLite: also called out as a known limitation.
- Adding TLS termination: expected to be handled by a reverse proxy in production.
