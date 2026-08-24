from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_RESERVED_OWNERS = {
    "about",
    "apps",
    "collections",
    "contact",
    "customer-stories",
    "enterprise",
    "events",
    "explore",
    "features",
    "login",
    "marketplace",
    "new",
    "notifications",
    "orgs",
    "pricing",
    "search",
    "sessions",
    "settings",
    "site",
    "sponsors",
    "topics",
    "trending",
    "users",
}
_SKIPPED_PARTS = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
    "venv",
}
_SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".ex",
    ".exs",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".php",
    ".pl",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".sql",
    ".svelte",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
_MANIFEST_NAMES = {
    ".editorconfig",
    ".gitignore",
    "cargo.toml",
    "compose.yml",
    "compose.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "dockerfile",
    "go.mod",
    "makefile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
}
_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "jsx",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "tsx",
}


class GitHubRepositoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubRepositoryRef:
    owner: str
    repo: str

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    @property
    def clone_url(self) -> str:
        return f"{self.web_url}.git"


@dataclass(frozen=True)
class RepositorySnapshot:
    markdown: str
    commit: str
    included_files: tuple[str, ...]
    skipped_files: int
    checkout_bytes: int
    truncated: bool
    cleanup_confirmed: bool = False


def parse_github_repository_url(url: str) -> GitHubRepositoryRef | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or host != "github.com":
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[:2]
    repo = repo.removesuffix(".git")
    if (
        owner.lower() in _RESERVED_OWNERS
        or not owner
        or not repo
        or not _NAME.fullmatch(owner)
        or not _NAME.fullmatch(repo)
    ):
        return None
    return GitHubRepositoryRef(owner=owner, repo=repo)


def _file_priority(path: PurePosixPath) -> int | None:
    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & _SKIPPED_PARTS:
        return None
    name = path.name.lower()
    if name.startswith("readme"):
        return 0
    if name in _MANIFEST_NAMES:
        return 1
    if path.suffix.lower() in _SOURCE_EXTENSIONS:
        return 2
    return None


def _tracked_paths(payload: bytes) -> list[PurePosixPath]:
    output: list[PurePosixPath] = []
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            continue
        if _file_priority(path) is not None:
            output.append(path)
    return sorted(output, key=lambda item: (_file_priority(item), str(item).casefold(), str(item)))


def _directory_size(root: Path, maximum: int) -> int:
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                details = entry.stat(follow_symlinks=False)
                total += details.st_size
                if total > maximum:
                    raise GitHubRepositoryError(
                        f"Repository checkout exceeds {maximum} bytes"
                    )
                if stat.S_ISDIR(details.st_mode):
                    pending.append(Path(entry.path))
    return total


def _read_text_file(path: Path, maximum: int) -> str | None:
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_size > maximum:
        return None
    with path.open("rb") as handle:
        payload = handle.read(maximum + 1)
    if len(payload) > maximum or b"\0" in payload:
        return None
    text = payload.decode("utf-8", "replace")
    if text.count("\ufffd") > max(10, len(text) // 100):
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _fence(text: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


def _file_section(path: PurePosixPath, text: str) -> str:
    if path.name.lower().startswith("readme"):
        return f"## README: {path}\n\n{text}\n"
    fence = _fence(text)
    language = _LANGUAGES.get(path.suffix.lower(), "text")
    kind = "Manifest" if _file_priority(path) == 1 else "Source"
    return f"## {kind}: {path}\n\n{fence}{language}\n{text}\n{fence}\n"


def _render_repository(
    checkout: Path,
    ref: GitHubRepositoryRef,
    commit: str,
    tracked_payload: bytes,
    *,
    checkout_bytes: int,
    max_files: int,
    max_file_bytes: int,
    max_chars: int,
) -> RepositorySnapshot:
    candidates = _tracked_paths(tracked_payload)
    included: list[str] = []
    sections: list[str] = []
    body_chars = 0
    truncated = False
    for relative in candidates:
        if len(included) >= max_files:
            truncated = True
            break
        try:
            text = _read_text_file(checkout.joinpath(*relative.parts), max_file_bytes)
        except OSError:
            continue
        if not text:
            continue
        section = _file_section(relative, text)
        # Reserve room for repository metadata and the selected-file list.
        reserve = 1500 + sum(len(path) + 3 for path in [*included, str(relative)])
        if body_chars + len(section) + reserve > max_chars:
            truncated = True
            break
        included.append(str(relative))
        sections.append(section)
        body_chars += len(section)
    if not sections:
        raise GitHubRepositoryError("Repository has no readable README, manifest, or source files")

    skipped = max(0, len(candidates) - len(included))
    header = (
        f"# GitHub repository: {ref.owner}/{ref.repo}\n\n"
        f"- Repository: {ref.web_url}\n"
        f"- Commit: `{commit}`\n"
        "- Clone depth: `1`\n"
        f"- Included files: `{len(included)}`\n"
        f"- Skipped candidate files: `{skipped}`\n"
        f"- Truncated by limits: `{'yes' if truncated else 'no'}`\n\n"
        "## Selected repository files\n\n"
        + "\n".join(f"- `{path}`" for path in included)
        + "\n\n"
    )
    markdown = header + "\n".join(sections)
    if len(markdown) < 400:
        raise GitHubRepositoryError("Structured repository text is below the minimum length")
    return RepositorySnapshot(
        markdown=markdown,
        commit=commit,
        included_files=tuple(included),
        skipped_files=skipped,
        checkout_bytes=checkout_bytes,
        truncated=truncated,
    )


def _force_remove(function, path: str, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    function(path)


def _remove_tree(path: Path) -> None:
    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_force_remove)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.1)


async def _cleanup_directory(path: Path) -> None:
    cleanup = asyncio.create_task(asyncio.to_thread(_remove_tree, path))
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        # A second cancellation must not orphan a checkout that the first one is already
        # cleaning. Wait for the filesystem operation, then preserve cancellation.
        await cleanup
        raise


async def _finish_process(process, communication: asyncio.Task) -> tuple[bytes, bytes]:
    if process.returncode is None:
        process.kill()
    return await communication


async def _run_command(
    *args: str,
    timeout_s: float,
    env: dict[str, str] | None = None,
) -> bytes:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    communication = asyncio.create_task(process.communicate())
    try:
        done, _ = await asyncio.wait({communication}, timeout=timeout_s)
    except asyncio.CancelledError:
        await _finish_process(process, communication)
        raise
    if not done:
        await _finish_process(process, communication)
        raise GitHubRepositoryError(f"git command timed out after {timeout_s:g} seconds")
    stdout, stderr = communication.result()
    if process.returncode:
        detail = stderr.decode("utf-8", "replace").strip()[-1200:]
        raise GitHubRepositoryError(detail or f"git exited with {process.returncode}")
    return stdout


async def clone_and_render_repository(
    ref: GitHubRepositoryRef,
    *,
    timeout_s: float,
    max_repository_bytes: int,
    max_files: int,
    max_file_bytes: int,
    max_chars: int,
) -> RepositorySnapshot:
    git = shutil.which("git")
    if not git:
        raise GitHubRepositoryError("git executable is not installed")

    workspace = Path(tempfile.mkdtemp(prefix="research-github-"))
    checkout = workspace / "repository"
    environment = os.environ.copy()
    environment.update(
        {
            "GCM_INTERACTIVE": "Never",
            "GIT_LFS_SKIP_SMUDGE": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    snapshot: RepositorySnapshot | None = None
    try:
        await _run_command(
            git,
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--no-tags",
            "--quiet",
            "--config",
            "core.autocrlf=false",
            "--",
            ref.clone_url,
            str(checkout),
            timeout_s=timeout_s,
            env=environment,
        )
        checkout_bytes = await asyncio.to_thread(
            _directory_size, workspace, max_repository_bytes
        )
        detail_timeout = min(10.0, timeout_s)
        commit = (
            await _run_command(
                git,
                "-C",
                str(checkout),
                "rev-parse",
                "HEAD",
                timeout_s=detail_timeout,
                env=environment,
            )
        ).decode("ascii", "replace").strip()
        tracked = await _run_command(
            git,
            "-C",
            str(checkout),
            "ls-files",
            "-z",
            timeout_s=detail_timeout,
            env=environment,
        )
        snapshot = await asyncio.to_thread(
            _render_repository,
            checkout,
            ref,
            commit,
            tracked,
            checkout_bytes=checkout_bytes,
            max_files=max_files,
            max_file_bytes=max_file_bytes,
            max_chars=max_chars,
        )
    finally:
        await _cleanup_directory(workspace)
    if snapshot is None:
        raise GitHubRepositoryError("Repository snapshot was not produced")
    return replace(snapshot, cleanup_confirmed=True)
