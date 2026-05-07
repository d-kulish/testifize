from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testifize_pipeline.config import load_dotenv
from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileConfig


SNAPSHOT_PATH = Path("data/state/sharefile_snapshot_latest.json")
USERS_PATH = Path("data/state/sharefile_users_latest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache ShareFile user metadata for mirrored file uploaders.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    snapshot = _load_json(repo_root / SNAPSHOT_PATH)
    user_ids = sorted(
        {
            raw["LastModifiedByUserID"]
            for row in snapshot.get("files", [])
            if isinstance((raw := row.get("raw_metadata")), dict) and raw.get("LastModifiedByUserID")
        }
    )

    client = ShareFileClient(ShareFileConfig.from_env(load_dotenv(repo_root / ".env")))
    client.authenticate()

    users_by_id = {}
    failures = []
    for user_id in user_ids:
        status, body, _ = client._request_json("GET", f"{client.base_url}/sf/v3/Users({user_id})")
        if status != 200:
            failures.append({"user_id": user_id, "status": status, "body": body})
            continue
        users_by_id[user_id] = _user_record(body)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot_run_id": snapshot.get("run_id", ""),
        "user_count": len(users_by_id),
        "failure_count": len(failures),
        "users_by_id": users_by_id,
        "failures": failures,
    }
    path = repo_root / USERS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"users={len(users_by_id)} failures={len(failures)} path={USERS_PATH}")
    return 1 if failures else 0


def _user_record(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("Id", ""),
        "full_name": raw.get("FullName", ""),
        "short_name": raw.get("FullNameShort", ""),
        "first_name": raw.get("FirstName", ""),
        "last_name": raw.get("LastName", ""),
        "email": raw.get("Email") or raw.get("Username") or "",
        "username": raw.get("Username", ""),
        "company": raw.get("Company", ""),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
