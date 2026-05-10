from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class GitHubUrlError(ValueError):
    pass


class GitCloneError(RuntimeError):
    pass


@dataclass
class GitHubRepoRef:
    owner: str
    repo: str
    original_url: str
    ref: str | None = None
    subpath: str | None = None

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def slug(self) -> str:
        parts = [self.owner, self.repo]
        if self.ref:
            parts.append(_slugify(self.ref))
        return "__".join(parts)


def parse_github_url(url: str) -> GitHubRepoRef:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        raise GitHubUrlError("Expected a public GitHub URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise GitHubUrlError("GitHub URL must include owner and repository.")

    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    ref = None
    subpath = None

    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref = parts[3]
        if len(parts) > 4:
            subpath = "/".join(parts[4:])

    return GitHubRepoRef(
        owner=owner,
        repo=repo,
        original_url=url,
        ref=ref,
        subpath=subpath,
    )


def clone_repository(repo_ref: GitHubRepoRef, destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "clone", "--depth", "1", repo_ref.canonical_url, str(destination)])

    if repo_ref.ref:
        _run_git(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", repo_ref.ref])
        _run_git(["git", "-C", str(destination), "checkout", "FETCH_HEAD"])

    return destination


def _run_git(command: list[str]) -> None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise GitCloneError("git is required but was not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() or exc.stdout.strip() or "git command failed"
        raise GitCloneError(stderr) from exc
    else:
        if completed.returncode != 0:
            raise GitCloneError(completed.stderr.strip() or "git command failed")


def _slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "ref"
