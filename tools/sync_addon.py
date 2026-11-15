"""Synchronize only allowlisted runtime sources into the public add-on context."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ('ai','analytics','bot','connectors','knowledge','storage','training_plan')
MODULES = ('main.py','config.py')


def runtime_paths():
    return [Path(name) for name in MODULES] + [p.relative_to(ROOT) for package in PACKAGES
                                              for p in (ROOT/package).rglob('*.py')]


def sync():
    for relative in runtime_paths():
        destination=ROOT/'dimi_health_assistant'/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,destination)


if __name__ == '__main__':
    sync()
