"""Verified, repeatable private-file migration without overwriting target changes."""
import hashlib
from pathlib import Path
import shutil
import sqlite3


def migrate_files(source: Path, target: Path) -> int:
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Source and target must be separate directories')
    files = [p for p in source.rglob('*') if p.is_file() and not p.is_symlink()
             and '.garminconnect' not in p.parts and not p.name.endswith(('-wal','-shm'))]
    # Preflight all collisions before changing any target file.
    for path in files:
        destination = target / path.relative_to(source)
        if destination.exists():
            if path.suffix in ('.sqlite3','.db'):
                with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as src, sqlite3.connect(f'file:{destination}?mode=ro',uri=True) as dst:
                    equal = '\n'.join(src.iterdump()) == '\n'.join(dst.iterdump())
            else:
                equal = path.read_bytes() == destination.read_bytes()
            if not equal:
                raise ValueError('Migration conflict: target has changed; preserve both copies')
    for path in files:
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():
            if path.suffix in ('.sqlite3','.db'):
                with sqlite3.connect(f'file:{path}?mode=ro',uri=True) as src, sqlite3.connect(destination) as dst:
                    src.backup(dst)
            else:
                shutil.copy2(path,destination)
        if path.suffix not in ('.sqlite3','.db'):
            assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(destination.read_bytes()).digest()
    return len(files)
