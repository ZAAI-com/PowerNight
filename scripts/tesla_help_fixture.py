#!/usr/bin/env python3
"""
Local stand-in for Tesla's sign-in redirect, for capturing help screenshots.

Opening http://127.0.0.1:8765/authorize answers with a 302 redirect to
tesla://auth/callback?code=EXAMPLE-CODE&state=EXAMPLE-STATE, the same kind of
redirect Tesla sends after signing in. Browsers then show the same Console
and Network output as in the real flow, without any real authorization code.
See docs/tesla-help-screenshots.md.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CALLBACK = 'tesla://auth/callback?code=EXAMPLE-CODE&state=EXAMPLE-STATE&issuer=https%3A%2F%2Fauth.tesla.com%2Foauth2%2Fv3'
PAGE = b"""<!doctype html><html><head><title>Tesla sign-in (fixture)</title></head>
<body style="font-family: system-ui; margin: 3rem">
<h1>Tesla sign-in fixture</h1>
<p>Open the developer tools (Console and Network), then click the button.</p>
<p><a href="/authorize" style="font-size: 1.2rem">Sign in</a></p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith('/authorize'):
            self.send_response(302)
            self.send_header('Location', CALLBACK)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(PAGE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Fixture running at http://127.0.0.1:{args.port}/ (Ctrl+C to stop)')
    server.serve_forever()


if __name__ == '__main__':
    main()
