"""Install a personal copy: python -m knowledge.import_epub book.epub --data-dir ./data."""

import argparse
import os
import shutil
from pathlib import Path

from .library import BOOK_NAME, KnowledgeBase, read_epub


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("epub", type=Path)
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "./data"))
    args = parser.parse_args()
    read_epub(args.epub)  # Validate before replacing the installed source.
    directory = Path(args.data_dir) / "knowledge"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / BOOK_NAME
    if args.epub.resolve() != target.resolve():
        temporary = directory / ".import.epub"
        shutil.copyfile(args.epub, temporary)
        temporary.chmod(0o600)
        temporary.replace(target)
    status = KnowledgeBase(args.data_dir).status()
    print(f"Imported: {status['title']} ({status['sections']} sections). Private file: {target.resolve()}")


if __name__ == "__main__":
    main()
