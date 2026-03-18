from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GitRepoInfo:
    local_path: Path
    remote_url: str | None
    branch: str | None
    commit_sha: str | None
    repo_id: str      

def clone_or_update(
    url: str,
    dest_dir: Path,
    branch: str | None = None,
    depth: int | None = 1,
) -> GitRepoInfo:
    try:
        from dulwich import porcelain
        from dulwich.repo import Repo as DulwichRepo
    except ImportError as exc:
        raise RuntimeError(
            "dulwich is required for git cloning. "
            "Install it with: pip install dulwich"
        ) from exc

    slug = _url_to_slug(url)
    local_path = dest_dir / slug

    if local_path.exists() and (local_path / ".git").exists():
        logger.info("Repo already cloned at %s — fetching updates.", local_path)
        _fetch_updates(local_path, url, branch)
    else:
        logger.info("Cloning %s → %s (depth=%s, branch=%s)", url, local_path, depth, branch)
        local_path.mkdir(parents=True, exist_ok=True)
        _do_clone(url, local_path, branch, depth)

    return get_repo_info(local_path, remote_url=url)

def get_repo_info(local_path: Path, remote_url: str | None = None) -> GitRepoInfo:
    try:
        from dulwich.repo import Repo as DulwichRepo

        repo = DulwichRepo(str(local_path))

        try:
            head_sha = repo.head().decode("utf-8")
        except Exception:
            head_sha = None

        try:
            refs = repo.refs
            branch = refs.get_symrefs().get(b"HEAD", b"").decode("utf-8")
            branch = branch.replace("refs/heads/", "") or None
        except Exception:
            branch = None

        if remote_url is None:
            try:
                cfg = repo.get_config()
                remote_url = cfg.get((b"remote", b"origin"), b"url").decode("utf-8")
            except Exception:
                remote_url = None

        repo.close()

    except Exception as exc:
        logger.warning("Could not read git metadata from %s: %s", local_path, exc)
        head_sha = None
        branch = None

    slug = _url_to_slug(remote_url) if remote_url else local_path.name
    return GitRepoInfo(
        local_path=local_path,
        remote_url=remote_url,
        branch=branch,
        commit_sha=head_sha,
        repo_id=_sanitise_slug(slug),
    )

def _do_clone(url: str, dest: Path, branch: str | None, depth: int | None) -> None:
    from dulwich import porcelain

    kwargs: dict = {}
    if branch:
        kwargs["branch"] = branch.encode()
    if depth:
        kwargs["depth"] = depth

    try:
        porcelain.clone(url, str(dest), **kwargs)
    except Exception as exc:
        import shutil
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"Failed to clone {url}: {exc}") from exc


def _fetch_updates(local_path: Path, url: str, branch: str | None) -> None:
    from dulwich import porcelain

    try:
        porcelain.fetch(str(local_path), url)
        if branch:
            porcelain.reset(str(local_path), "hard")
    except Exception as exc:
        logger.warning("Could not fetch updates for %s: %s. Using cached version.", local_path, exc)

def _url_to_slug(url: str) -> str:
    url = re.sub(r"\.git$", "", url.strip())
    url = re.sub(r"^git@([^:]+):", r"\1/", url)
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^ssh://", "", url)
    slug = re.sub(r"[/\\:@]", "-", url)
    slug = re.sub(r"-+", "-", slug).strip("-")

    return slug

def _sanitise_slug(slug: str) -> str:
    slug = re.sub(r"[^\w\-]", "_", slug)
    return slug[:128] 