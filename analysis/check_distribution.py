"""Check local distribution inputs using only the Python standard library."""
from pathlib import Path
import hashlib
import json
import sys


def check(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'docs/private-resources.json').read_text(encoding='utf-8'))
    missing, changed = [], []
    for entry in manifest['files']:
        path = root / entry['path']
        if not path.is_file():
            missing.append(entry['path'])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            changed.append(entry['path'])
    for name in ('main.py', 'packstudio/release.py', 'packstudio/data/version_catalog.json',
                 'packstudio/data/slice_rules.json', 'packstudio/data/Mojang-slicer-LICENSE',
                 'docs/resource-identities.tsv'):
        if not (root / name).is_file():
            missing.append(name)
    if missing or changed:
        print('Distribution inputs need review:')
        for name in missing:
            print('  MISSING: ' + name)
        for name in changed:
            print('  CHANGED: ' + name)
        print('See docs/private-resources.json and THIRD_PARTY_NOTICES.md.')
        return False
    print('Distribution inputs match the reviewed resource manifest.')
    return True


if __name__ == '__main__':
    sys.exit(0 if check(Path(__file__).resolve().parents[1]) else 1)
