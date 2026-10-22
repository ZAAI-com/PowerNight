# Capturing the Tesla sign-in help screenshots

The Settings sign-in help can show either schematic diagrams (the default) or
real browser screenshots. Both are built in so the choice can be made later.

## Compare the two in the running app

In the browser console on the PowerNight page:

```js
localStorage.setItem('powernight_help_visual', 'screenshot') // or 'diagram'
```

Reload Settings and start a sign-in. Browsers without a screenshot keep the
diagram. To change the default for everyone, set `TESLA_HELP_VISUAL` in
`src/powernight/web/src/components/tesla/help/helpVisual.ts`.

## Capture without a real Tesla code

`scripts/tesla_help_fixture.py` answers like Tesla does after signing in: a
redirect to `tesla://auth/callback?code=EXAMPLE-CODE&state=EXAMPLE-STATE`.

```bash
python3 scripts/tesla_help_fixture.py   # http://127.0.0.1:8765/
```

For each browser, open the fixture, open the developer tools on the Console
tab, click "Sign in", and capture the window with `screencapture -w file.png`
(click the browser window):

| Browser | Open with developer tools | Save as |
|---|---|---|
| Chrome / Edge | `open -na "Google Chrome" --args --auto-open-devtools-for-tabs http://127.0.0.1:8765/` | `chromium-console.png` |
| Firefox | `open -na Firefox --args -devtools http://127.0.0.1:8765/` | `firefox-console.png` |
| Safari | Develop > Show JavaScript Console (turn on "Show features for web developers" first) | `safari-console.png` |

Save the files in `src/powernight/web/src/assets/tesla-help/`, keep them small
(crop to the page and the Console, about 1000 px wide), and rebuild with
`./build.sh --no-docker`.

Before publishing, check the wording of the help steps against one real Tesla
sign-in in each browser; developer tools change between browser versions.
