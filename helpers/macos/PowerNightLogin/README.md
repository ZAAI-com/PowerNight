# PowerNight Login (experimental macOS helper)

PowerNight Login signs in to Tesla in its own window and hands the result back
to your PowerNight server, so you do not have to copy the `tesla://` link out
of the browser's developer tools.

It is a prototype. The manual steps in PowerNight Settings and the pypowerwall
token import keep working on every platform, with or without the helper.

## How it works

1. In PowerNight Settings, start the Tesla sign-in, turn on
   "Try the experimental Mac helper" and click "Sign In with the Mac Helper".
2. PowerNight creates a short-lived handoff for that one sign-in attempt and
   opens `powernight-login://start?v=1&origin=<your PowerNight>&handoff=<...>`.
3. The first time a PowerNight address is used, the helper asks you to confirm
   it. Only continue if you just clicked the button in PowerNight.
4. The helper asks PowerNight for the Tesla sign-in page of that attempt,
   checks that it really is Tesla's page, and shows it.
5. When Tesla redirects to `tesla://auth/callback`, the helper stops the
   redirect and sends it to PowerNight. Return to your browser to choose the
   energy site (PowerNight picks it automatically when there is only one).

PowerNight keeps PKCE, the token exchange, saving the credentials and the site
selection. The helper never receives the PowerNight API key, the setup session
ID or any Tesla token.

## Security model

- **Handoff:** single attempt, expires with it (10 minutes), stored on the
  server only as a hash, sent only in the `X-PowerNight-Handoff` header and
  consumed once the result is accepted.
- **Trust on first use:** every new PowerNight address needs an explicit
  confirmation. Without it, any web page could open a launch link naming its
  own server and receive your Tesla sign-in result.
- **Transport:** HTTPS with the system's certificate checks (no bypass for
  self-signed certificates). Plain HTTP is accepted only for local-network
  hosts (private or link-local addresses, `.local` and single-label names)
  and only after you allow it for that server in the confirmation dialog. All
  redirects from PowerNight are refused.
- **Web view:** a non-persistent website data store (no cookies are kept), the
  main frame restricted to Tesla's HTTPS pages, and the `tesla://` redirect
  captured instead of loaded.
- **Nothing secret** is logged, copied to the clipboard or stored on disk.

## Build and install

Requires macOS 13 or later and Xcode (or the Swift toolchain with XCTest).

```bash
cd helpers/macos/PowerNightLogin
swift test                       # policy unit tests
./scripts/build-app.sh           # build/PowerNight Login.app (ad-hoc signed)
./scripts/build-app.sh --universal   # Apple silicon + Intel
```

The build script registers the `powernight-login://` link with Launch
Services. Move the app to `/Applications` if you like and open it once with
right-click > Open (it is not notarized). Signing with a Developer ID and
notarization belong to the distribution gate, after validation with a real
Tesla account (including MFA) and a real PowerNight server.

## Not covered

Windows and Linux use the guided web flow or the token import.
