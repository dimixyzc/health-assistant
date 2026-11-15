"""Refresh the existing private Momentum snapshot using shared data access."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('refresh_data.py')),run_name='__main__')
