"""Package deployment files with checksums without publishing a release."""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ('docker-compose.yml', 'compose.release.yml', '.env.example', 'config.example.yaml')


def package(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    checksums = []
    for name in FILES:
        data = (ROOT / name).read_bytes()
        (output / name).write_bytes(data)
        checksums.append(f'{hashlib.sha256(data).hexdigest()}  {name}\n')
    (output / 'SHA256SUMS').write_text(''.join(checksums))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.context/release/assets')
    package(parser.parse_args().output_dir)
