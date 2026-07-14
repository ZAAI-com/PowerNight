"""
Structural smoke tests for the Flask route surface.

Two guards:
1. Every parameterless GET route must respond without a server error
   (catches undefined-helper / import-time bugs in endpoint bodies).
2. Every string-literal API path used by the React frontend
   (src/powernight/web/src/utils/api.ts) must match a registered Flask rule.
"""

import re
from pathlib import Path

import pytest
import yaml
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_TS_PATH = PROJECT_ROOT / "src" / "powernight" / "web" / "src" / "utils" / "api.ts"

# Known non-structural 5xx responses. GET /api/auth/tesla/powerwalls maps the
# perfectly normal "no Tesla auth data stored yet" state to HTTP 500 by design
# (auth_api.py get_powerwalls returns 500 whenever the pypowerwall connection
# test fails). That is an API design wart, not a routing/structure bug, so it
# is exempted here instead of being asserted on.
KNOWN_5XX_ROUTES = {
    "/api/auth/tesla/powerwalls",
}

VALID_CONFIG = {
    "powerwall": {"tesla_email": "test@example.com"},
    "automation": {"enabled": False, "schedule": []},
    "web_interface": {"enabled": True, "host": "0.0.0.0", "port": 8080},
    "logging": {"level": "INFO", "file_path": "logs/powernight.log"},
    "monitoring": {"enabled": False},
}


@pytest.fixture(autouse=True)
def isolated_runtime_state(tmp_path, monkeypatch):
    """
    Mirror application startup without touching the repository working tree:
    - keep the SQLite database and Tesla auth files inside tmp_path
    - load a valid configuration into the ConfigManager singleton
      (main.py does this before create_app in production)
    """
    from powernight.core.config.manager import ConfigManager
    import powernight.core.config.manager as manager_module
    from powernight.core.database import connection

    monkeypatch.setenv("POWERNIGHT_DATA_PATH", str(tmp_path))
    connection.close_database()

    config_path = tmp_path / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(VALID_CONFIG, f)

    ConfigManager._instance = None
    manager_module._config_manager = None
    ConfigManager().load_config(config_path)

    yield

    ConfigManager._instance = None
    manager_module._config_manager = None
    connection.close_database()


def test_parameterless_get_routes_do_not_return_server_errors(app, client):
    """Issue a GET against every static route and reject 5xx responses."""
    failures = []
    checked = 0

    for rule in app.url_map.iter_rules():
        if rule.arguments:
            continue  # needs path parameters, not smoke-testable generically
        if "GET" not in (rule.methods or set()):
            continue
        if rule.rule in KNOWN_5XX_ROUTES:
            continue

        checked += 1
        try:
            response = client.get(rule.rule)
            status = response.status_code
        except Exception as exc:  # propagated in testing mode instead of a 500
            failures.append(f"GET {rule.rule} raised {type(exc).__name__}: {exc}")
            continue

        # 503 is a legitimate "degraded/unavailable" health answer; every
        # other 5xx means the endpoint itself is broken.
        if status >= 500 and status != 503:
            failures.append(f"GET {rule.rule} returned {status}")

    assert checked > 0, "url_map produced no parameterless GET routes to check"
    assert not failures, "Routes returned server errors:\n" + "\n".join(failures)


# Matches this.client.get/post/put/patch/delete(...) calls, including ones
# with TypeScript generics between the method name and the opening paren.
CLIENT_CALL_RE = re.compile(
    r"this\.client\.(get|post|put|patch|delete)\b[^(]*\(\s*(['\"`])([^'\"`]*)\2"
)
# Matches fetch('...') style calls.
FETCH_RE = re.compile(r"\bfetch\(\s*(['\"`])([^'\"`]*)\1")


def extract_frontend_api_calls():
    """
    Extract (METHOD, absolute_path) pairs from the frontend API client.

    Template literals containing ${...} are skipped (dynamic segments),
    and query strings are stripped.
    """
    source = API_TS_PATH.read_text()
    calls = set()

    for match in CLIENT_CALL_RE.finditer(source):
        method, path = match.group(1), match.group(3)
        if "${" in path:
            continue
        path = path.split("?")[0]
        if not path.startswith("/"):
            continue
        # axios client is created with baseURL '/api/v1'
        calls.add((method.upper(), "/api/v1" + path))

    for match in FETCH_RE.finditer(source):
        path = match.group(2)
        if "${" in path:
            continue
        path = path.split("?")[0]
        if not path.startswith("/"):
            continue
        calls.add(("GET", path))

    return sorted(calls)


def test_frontend_api_paths_match_backend_routes(app):
    """Every static path the frontend calls must resolve to a Flask rule."""
    calls = extract_frontend_api_calls()
    assert calls, f"No API calls extracted from {API_TS_PATH}"

    adapter = app.url_map.bind("localhost")
    missing = []

    for method, path in calls:
        try:
            adapter.match(path, method=method)
        except RequestRedirect:
            continue  # trailing-slash redirect still means the route exists
        except MethodNotAllowed:
            missing.append(f"{method} {path} (path exists but method not allowed)")
        except NotFound:
            missing.append(f"{method} {path} (no matching Flask rule)")

    assert not missing, (
        "Frontend api.ts references routes the backend does not serve:\n"
        + "\n".join(missing)
    )
