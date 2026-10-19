"""Exercise a release image with isolated Compose volumes and no Tesla access."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SEED_LEGACY = '''
import json, sqlite3
from pathlib import Path
root = Path('/data')
with sqlite3.connect(root / 'powernight.db') as db:
    db.executescript("""
        CREATE TABLE schedule_entries (id TEXT PRIMARY KEY);
        INSERT INTO schedule_entries VALUES ('legacy-schedule');
        CREATE TABLE task_presets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, command TEXT NOT NULL,
            command_params JSON, default_time TEXT, is_builtin BOOLEAN,
            sort_order INTEGER, created_at DATETIME, updated_at DATETIME
        );
        INSERT INTO task_presets VALUES
            ('oldest', 'Existing preset', 'reserve', '{"reserve":20}', NULL, 0, 100, NULL, NULL),
            ('duplicate', 'Existing preset', 'reserve', '{"reserve":30}', NULL, 0, 100, NULL, NULL);
        CREATE TABLE task_executions (
            id TEXT PRIMARY KEY, task_id TEXT, status TEXT NOT NULL,
            started_at DATETIME, completed_at DATETIME, result JSON,
            error_message TEXT, created_at DATETIME, updated_at DATETIME
        );
    """)
# Deliberately invalid test-only auth data: startup fails before any cloud call.
(root / '.pypowerwall.auth').write_text(json.dumps({'release_smoke': True}))
(root / '.pypowerwall.site').write_text('release-smoke-site')
'''
SNAPSHOT = '''
import hashlib, json, sqlite3
from pathlib import Path
root = Path('/data')
assert root.joinpath('powernight.db').is_file(), 'SQLite must persist on /data'
with sqlite3.connect(root / 'powernight.db') as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not db.execute("SELECT name FROM sqlite_master WHERE name='schedule_entries'").fetchall()
    columns = {row[1] for row in db.execute('PRAGMA table_info(task_executions)')}
    assert {'execution_type', 'task_name', 'command', 'command_params', 'api_response'} <= columns
    assert db.execute("SELECT id FROM task_presets WHERE name='Existing preset'").fetchall() == [('oldest',)]
    tasks = db.execute('SELECT id, name, enabled FROM tasks ORDER BY id').fetchall()
    assert tasks and all(not row[2] for row in tasks), 'Test tasks must remain disabled'
    presets = db.execute('SELECT id, name FROM task_presets ORDER BY id').fetchall()
files = {name: hashlib.sha256(root.joinpath(name).read_bytes()).hexdigest()
         for name in ('.pypowerwall.auth', '.pypowerwall.site', '.flask_secret')}
print(json.dumps({'tasks': tasks, 'presets': presets, 'files': files}))
'''


def request(base, path, key='', payload=None, expected=200):
    headers = {'X-API-Key': key} if key else {}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(base + path, headers=headers,
                  data=json.dumps(payload).encode() if payload is not None else None)
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        body = response.read().decode()
        assert response.status == expected, f'{path}: expected {expected}, got {response.status}'
    return json.loads(body) if body.startswith('{') else body


def exercise(image, output, protected):
    mode = 'protected' if protected else 'open'
    project = f'powernight-release-{uuid4().hex[:10]}'
    key = 'release-smoke-only-key' if protected else ''
    env = dict(os.environ, POWERNIGHT_TEST_IMAGE=image, POWERNIGHT_TEST_API_KEY=key)
    prefix = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'compose.release-test.yml')]

    def compose(*args, capture=False):
        result = subprocess.run(prefix + list(args), env=env, cwd=ROOT, check=True,
                                text=True, stdout=subprocess.PIPE if capture else None)
        return result.stdout.strip() if capture else None

    try:
        compose('run', '--rm', '--no-deps', 'PowerNight', 'python', '-c', SEED_LEGACY)
        compose('up', '-d', '--wait', '--wait-timeout', '90')
        port = compose('port', 'PowerNight', '8020', capture=True).rsplit(':', 1)[1]
        base = f'http://127.0.0.1:{port}'
        version = request(base, '/version')['version']
        assert request(base, '/health')['status'] == 'healthy'
        for path in ('/', '/planner', '/history', '/settings'):
            html = request(base, path)
            assert '<div id="root"></div>' in html
        for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', html):
            request(base, asset)
        if protected:
            request(base, '/api/v1/tasks', expected=401)
            request(base, '/api/v1/tasks', key='incorrect-key', expected=401)
        assert request(base, '/api/v1/tasks', key)['data']['total'] == 0
        task = request(base, '/api/v1/tasks', key, {
            'name': 'Release smoke task', 'time': '23:59', 'command': 'reserve',
            'command_params': {'reserve': 0}, 'enabled': False,
        }, expected=201)['data']
        preset = {'name': 'Release smoke preset', 'command': 'reserve', 'command_params': {'reserve': 40}}
        request(base, '/api/v1/tasks/presets', key, preset, expected=201)
        duplicate = request(base, '/api/v1/tasks/presets', key, preset, expected=409)
        assert 'INSERT' not in json.dumps(duplicate)
        request(base, '/api/v1/config/timezone', key, {'timezone': 'UTC'})
        if protected:
            compose('exec', '-T', 'PowerNight', 'python', '-c',
                    "from pathlib import Path; assert 'release-smoke-only-key' not in Path('/app/config/config.yaml').read_text()")
        before = json.loads(compose('exec', '-T', 'PowerNight', 'python', '-c', SNAPSHOT, capture=True))
        compose('stop', '--timeout', '10')
        compose('up', '-d', '--force-recreate', '--wait', '--wait-timeout', '90')
        port = compose('port', 'PowerNight', '8020', capture=True).rsplit(':', 1)[1]
        base = f'http://127.0.0.1:{port}'
        assert request(base, f"/api/v1/tasks/{task['id']}", key)['data']['name'] == task['name']
        after = json.loads(compose('exec', '-T', 'PowerNight', 'python', '-c', SNAPSHOT, capture=True))
        assert before == after, 'Data, auth artifacts, or Flask secret changed during recreation'
        result = {'mode': mode, 'version': version, 'passed': True,
                  'migration': 'synthetic legacy schema', 'container_recreation': True,
                  'persistent_sqlite': True, 'auth_artifacts': 'synthetic, no Tesla login',
                  'task_count': len(after['tasks']), 'preset_count': len(after['presets'])}
        print(json.dumps(result), flush=True)
        return result
    finally:
        logs = subprocess.run(prefix + ['logs', '--no-color'], env=env, cwd=ROOT,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (output / f'{mode}.log').write_text(logs.stdout)
        compose('down', '--volumes', '--remove-orphans')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='powernight-release:test')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.context/release/compose-smoke')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = [exercise(args.image, args.output_dir, protected) for protected in (False, True)]
    (args.output_dir / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
