"""Build-time inputs only; the application uses its bundled offline store."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'reference/各版本assets'

def source_directory(version):
    candidates=[path for path in (ROOT/version,ROOT/'更多版本'/version) if path.is_dir()]
    if len(candidates)!=1:
        raise ValueError(f'{version}: expected one reference directory, found {candidates}')
    path=candidates[0]
    if not (path/'minecraft').is_dir():raise ValueError(f'{version}: missing minecraft namespace')
    return path
