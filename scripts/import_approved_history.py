from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Import approved historical vendor CSVs into data/processed.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--processed-root", type=Path)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    source_root = args.source_root or repo_root / "_old" / "final"
    processed_root = args.processed_root or repo_root / "data" / "processed"
    if not source_root.exists():
        raise SystemExit(f"Missing source root: {source_root}")

    imported = 0
    for source_path in sorted(source_root.glob("*.csv")):
        vendor = source_path.stem
        destination = processed_root / vendor / source_path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        imported += 1
        print(f"imported {source_path.relative_to(repo_root)} -> {destination.relative_to(repo_root)}")

    print(f"approved_history_imported={imported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
