from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SYNC_STATE_PATH = Path("data/state/sharefile_sync_state.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update ShareFile mirror, profile, and uploader metadata.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    state_path = repo_root / SYNC_STATE_PATH
    started_at = datetime.now(timezone.utc)
    steps = []
    status = "success"

    for label, command in [
        ("mirror", [sys.executable, "scripts/mirror_sharefile.py", "--repo-root", str(repo_root)]),
        ("profile", [sys.executable, "scripts/profile_inbox.py", "--repo-root", str(repo_root)]),
        ("users", [sys.executable, "scripts/sync_sharefile_users.py", "--repo-root", str(repo_root)]),
    ]:
        result = run_step(label, command, repo_root)
        steps.append(result)
        if result["returncode"] != 0:
            status = "failed"
            break

    payload = {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"sync_status={status} state={SYNC_STATE_PATH}")
    return 0 if status == "success" else 1


def run_step(label: str, command: list[str], repo_root: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return {
        "label": label,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


if __name__ == "__main__":
    raise SystemExit(main())
