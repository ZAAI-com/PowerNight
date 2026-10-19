"""Release tags must agree with every packaged version, not only image labels."""

import json
from pathlib import Path
import runpy

import pytest


ROOT = Path(__file__).resolve().parents[2]
check_version = runpy.run_path(str(ROOT / 'scripts/check_release_version.py'))['check_version']


def test_current_release_versions_agree():
    check_version('2.0.0', ROOT)


@pytest.mark.parametrize('version', ['v2.0.0', '2.0.0-rc.1', '02.0.0', '2.0', '2.0.0\nunsafe'])
def test_release_rejects_nonstable_or_malformed_tags(version):
    with pytest.raises(ValueError, match='MAJOR.MINOR.PATCH'):
        check_version(version, ROOT)


@pytest.mark.parametrize('target', ['python', 'frontend', 'lock', 'lock_root', 'runtime'])
def test_release_rejects_version_drift(tmp_path, target):
    (tmp_path / 'src/powernight').mkdir(parents=True)
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "2.0.0"\n')
    (tmp_path / 'package.json').write_text(json.dumps({'version': '2.0.0'}))
    lock = {'version': '2.0.0', 'packages': {'': {'version': '2.0.0'}}}
    (tmp_path / 'src/powernight/__init__.py').write_text('__version__ = "2.0.0"\n')
    if target == 'python':
        (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "1.0.0"\n')
    elif target == 'frontend':
        (tmp_path / 'package.json').write_text(json.dumps({'version': '1.0.0'}))
    elif target == 'lock':
        lock['version'] = '1.0.0'
    elif target == 'lock_root':
        lock['packages']['']['version'] = '1.0.0'
    else:
        (tmp_path / 'src/powernight/__init__.py').write_text('__version__ = "1.0.0"\n')
    (tmp_path / 'package-lock.json').write_text(json.dumps(lock))
    with pytest.raises(ValueError, match='does not match source versions'):
        check_version('2.0.0', tmp_path)
