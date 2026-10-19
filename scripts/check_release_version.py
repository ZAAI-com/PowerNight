"""Fail a release when its tag and packaged version identifiers disagree."""

import argparse
import json
from pathlib import Path
import re
import tomllib


def check_version(version: str, root: Path) -> None:
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Use a stable MAJOR.MINOR.PATCH version without a v prefix')
    python_version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
    package = json.loads((root / 'package.json').read_text())
    lock = json.loads((root / 'package-lock.json').read_text())
    module_version = re.search(
        r'^__version__ = "([^"]+)"',
        (root / 'src/powernight/__init__.py').read_text(), re.MULTILINE,
    )
    versions = {
        'pyproject.toml': python_version,
        'package.json': package['version'],
        'package-lock.json': lock['version'],
        'package-lock.json root package': lock['packages']['']['version'],
        'powernight.__version__': module_version.group(1) if module_version else None,
    }
    mismatches = {name: actual for name, actual in versions.items() if actual != version}
    if mismatches:
        raise ValueError(f'Release {version} does not match source versions: {mismatches}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    args = parser.parse_args()
    try:
        check_version(args.version, Path(__file__).resolve().parents[1])
    except ValueError as error:
        parser.exit(1, f'{error}\n')
    print(f'Release {args.version} matches all source version identifiers')
