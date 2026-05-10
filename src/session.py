from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from github import GitHubRepoRef, clone_repository, parse_github_url
from models import TurnRecord, to_dict, turn_from_dict

SESSION_FILENAME = "session.json"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass
class InvestigationSession:
    session_dir: Path
    repo_ref: GitHubRepoRef
    repo_dir: Path
    created_at: str
    turns: list[TurnRecord] = field(default_factory=list)

    def append_turn(self, turn: TurnRecord) -> None:
        self.turns.append(turn)

    def save(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "session_dir": str(self.session_dir),
            "repo_ref": {
                "owner": self.repo_ref.owner,
                "repo": self.repo_ref.repo,
                "original_url": self.repo_ref.original_url,
                "ref": self.repo_ref.ref,
                "subpath": self.repo_ref.subpath,
            },
            "repo_dir": str(self.repo_dir),
            "created_at": self.created_at,
            "turns": [to_dict(turn) for turn in self.turns],
        }
        (self.session_dir / SESSION_FILENAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load(self, session_dir: Path) -> InvestigationSession:
        data = json.loads((session_dir / SESSION_FILENAME).read_text(encoding="utf-8"))
        repo_ref_data = data["repo_ref"]
        repo_ref = GitHubRepoRef(
            owner=repo_ref_data["owner"],
            repo=repo_ref_data["repo"],
            original_url=repo_ref_data["original_url"],
            ref=repo_ref_data.get("ref"),
            subpath=repo_ref_data.get("subpath"),
        )
        return InvestigationSession(
            session_dir=Path(data["session_dir"]),
            repo_ref=repo_ref,
            repo_dir=Path(data["repo_dir"]),
            created_at=data["created_at"],
            turns=[turn_from_dict(turn) for turn in data.get("turns", [])],
        )

    def load_by_id(self, session_id: str) -> InvestigationSession:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("Invalid session id.")

        session_dir = (self.root / session_id).resolve()
        if session_dir.parent != self.root or not (session_dir / SESSION_FILENAME).exists():
            raise FileNotFoundError(f"Unknown session: {session_id}")
        return self.load(session_dir)

    def load_or_create(self, target: str) -> InvestigationSession:
        target_path = Path(target)
        if (
            target_path.exists()
            and target_path.is_dir()
            and (target_path / SESSION_FILENAME).exists()
        ):
            return self.load(target_path.resolve())

        repo_ref = parse_github_url(target)
        session_dir = self.root / repo_ref.slug
        repo_dir = session_dir / "repo"

        if (session_dir / SESSION_FILENAME).exists():
            return self.load(session_dir)

        clone_repository(repo_ref, repo_dir)
        session = InvestigationSession(
            session_dir=session_dir,
            repo_ref=repo_ref,
            repo_dir=repo_dir,
            created_at=_utc_now(),
        )
        session.save()
        return session


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
