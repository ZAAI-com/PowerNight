# Security Guidelines

## ⚠️ **IMPORTANT: Security Assumptions**

PowerNight is intended for **trusted local networks** and supports optional API authentication:

- 🔐 **Credential-Driven Authentication**: With no configured credential, authentication is off. A nonempty `POWERNIGHT_API_KEY` or complete username/password pair automatically enables it. Explicitly enabling auth without usable credentials fails closed.
- 🔑 **Sending Credentials**: When authentication is enabled, use an `X-API-Key` header, `Authorization: Bearer <key>`, or HTTP Basic authentication with the configured username/password pair. `/health`, `/version`, SPA/static assets, `GET /api/v1/version-info.json`, and `GET /api/v1/config/timezone` and `/api/v1/config/timezones` are public metadata. Detailed `/api/v1/health` stays protected. All Tesla setup endpoints (start, callback, tokens, sites, complete, cancel, status and the Mac helper handoff) require app authentication when enabled, except for tokenless first-time bootstrap from loopback. Do not use detailed health as an unauthenticated probe.
- 🛡️ **Hardening Applied**: Security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy`) and rate limiting on auth/setup endpoints are applied in `web/middleware.py`. The Flask session secret is set from `FLASK_SECRET_KEY` or persisted under the data path.
- ✅ **Intended Use**: Deploy within your home/private network behind a firewall
- ❌ **NOT for Public Internet**: Do not expose PowerNight directly to the internet, even with the API key set

### Tesla Sign-In Attempts

- A sign-in attempt lives only in server memory for 10 minutes. The PKCE verifier and, after the code exchange, the pending Tesla tokens never leave the server and are wiped when the attempt completes, is cancelled or expires. A restart ends all pending attempts.
- Each authorization code is exchanged at most once. Responses and logs never include Tesla's error text, which can contain token values.
- Existing credentials are replaced only after Tesla accepted the new tokens and the chosen site is one Tesla listed for them. The auth and site files are replaced together (restored if either write fails) while the live session is swapped under its lock.
- The browser keeps only the setup session ID, email and setup expiry in `sessionStorage`; never callback links, tokens or the verifier.
- Setup endpoints are rate limited per client address: 20 requests a minute for changes, 120 a minute for status reads, 30 a minute for the Mac helper. Behind a reverse proxy all clients share these limits.
- The experimental Mac helper authenticates with a single-use handoff bound to one attempt (stored only as a hash, sent only in the `X-PowerNight-Handoff` header). It never receives the API key, the session ID or Tesla tokens. See [the helper README](../helpers/macos/PowerNightLogin/README.md).

### Token Storage

- Tesla OAuth tokens are stored as plain JSON in `.pypowerwall.auth` (teslapy cache format). They are **not encrypted at rest**: `pypowerwall`/`teslapy` read and rewrite this file directly, so encryption would break the Tesla cloud connection.
- Instead, tokens are protected with owner-only permissions: the auth/site files are `0o600` and the data directory is `0o700`.

### Deployment Security Best Practices

1. **Protect Shared Networks**: Set `POWERNIGHT_API_KEY` using `openssl rand -hex 32` when guests, IoT devices, VPN peers, or other untrusted clients can reach PowerNight
2. **Local Network Only**: Only accessible from your trusted home/office network
3. **Firewall Protection**: Use router/firewall rules to block external access to port 8020
4. **VPN for Remote Access**: Use VPN (WireGuard, OpenVPN) for secure remote access

⚠️ **Warning**: Exposing PowerNight directly to the internet without additional security measures could allow unauthorized control of your Tesla Powerwall.

---

## 🔒 **IMPORTANT: Remove All Sensitive Data Before Committing**

This repository should **NEVER** contain:
- Real Powerwall passwords
- API keys or tokens
- Personal credentials
- Production configuration with sensitive data

## ✅ **Security Checklist**

Before committing any changes, ensure:

- [ ] No real passwords in configuration files
- [ ] No API keys or tokens in code
- [ ] No personal credentials in examples
- [ ] All sensitive data replaced with placeholders
- [ ] Configuration files use example values only

---

**Remember: Security is everyone's responsibility!** 🛡️
