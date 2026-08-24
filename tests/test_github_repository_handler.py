from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest

import research_platform.acquisition as acquisition_module
import research_platform.github_repository as github_module
from research_platform.acquisition import ACQUISITION_STRATEGY_ORDER, AcquisitionService
from research_platform.config import Settings
from research_platform.github_repository import (
    GitHubRepositoryError,
    RepositorySnapshot,
    clone_and_render_repository,
    parse_github_repository_url,
)
from research_platform.schemas import ConnectorCandidate, SourceFamily


def _candidate(url: str = "https://github.com/openai/codex") -> ConnectorCandidate:
    return ConnectorCandidate(
        connector_id="github",
        family=SourceFamily.CODE_DATA,
        title="openai/codex",
        url=url,
        metadata={"size": 24},
    )


def _track_temp_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Path]:
    original = tempfile.mkdtemp
    created: list[Path] = []

    def tracked(*args, **kwargs):
        kwargs["dir"] = tmp_path
        path = Path(original(*args, **kwargs))
        created.append(path)
        return str(path)

    monkeypatch.setattr(github_module.tempfile, "mkdtemp", tracked)
    return created


def test_repository_url_parser_handles_subpaths_and_rejects_github_pages():
    ref = parse_github_repository_url(
        "https://www.github.com/OpenAI/codex.git/blob/main/README.md?plain=1"
    )
    assert ref is not None
    assert (ref.owner, ref.repo) == ("OpenAI", "codex")
    assert ref.web_url == "https://github.com/OpenAI/codex"
    assert parse_github_repository_url("https://github.com/search?q=codex") is None
    assert parse_github_repository_url("https://gitlab.com/openai/codex") is None


@pytest.mark.asyncio
async def test_clone_renders_tracked_files_and_removes_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    created = _track_temp_directories(monkeypatch, tmp_path)
    commands: list[tuple[str, ...]] = []

    class FakeProcess:
        def __init__(self, args: tuple[str, ...]):
            self.args = args
            self.returncode = None

        async def communicate(self):
            commands.append(self.args)
            if "clone" in self.args:
                checkout = Path(self.args[-1])
                (checkout / ".git" / "objects").mkdir(parents=True)
                (checkout / ".git" / "objects" / "pack").write_bytes(b"git objects")
                (checkout / "src").mkdir()
                (checkout / "vendor").mkdir()
                (checkout / "README.md").write_text(
                    "# Codex\n\n" + ("Repository architecture and usage. " * 30),
                    encoding="utf-8",
                )
                (checkout / "pyproject.toml").write_text("[project]\nname='codex'\n")
                (checkout / "src" / "app.py").write_text(
                    "def main():\n    return 'ok'\n", encoding="utf-8"
                )
                (checkout / "vendor" / "ignored.py").write_text("SECRET = 'vendor'\n")
                self.returncode = 0
                return b"", b""
            if "rev-parse" in self.args:
                self.returncode = 0
                return b"a" * 40 + b"\n", b""
            self.returncode = 0
            return (
                b"README.md\0pyproject.toml\0src/app.py\0vendor/ignored.py\0image.png\0",
                b"",
            )

        def kill(self):
            self.returncode = -9

    async def fake_subprocess(*args, **_kwargs):
        return FakeProcess(tuple(args))

    monkeypatch.setattr(github_module.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(github_module.asyncio, "create_subprocess_exec", fake_subprocess)
    ref = parse_github_repository_url("https://github.com/openai/codex")
    assert ref is not None
    snapshot = await clone_and_render_repository(
        ref,
        timeout_s=30,
        max_repository_bytes=10_000_000,
        max_files=20,
        max_file_bytes=100_000,
        max_chars=100_000,
    )

    clone_command = commands[0]
    assert clone_command[1:7] == (
        "clone", "--depth", "1", "--single-branch", "--no-tags", "--quiet"
    )
    assert "## README: README.md" in snapshot.markdown
    assert "## Manifest: pyproject.toml" in snapshot.markdown
    assert "## Source: src/app.py" in snapshot.markdown
    assert "vendor/ignored.py" not in snapshot.markdown
    assert snapshot.commit == "a" * 40
    assert snapshot.cleanup_confirmed is True
    assert created and all(not path.exists() for path in created)


@pytest.mark.asyncio
async def test_failed_clone_still_removes_temporary_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    created = _track_temp_directories(monkeypatch, tmp_path)

    class FailedProcess:
        returncode = None

        async def communicate(self):
            self.returncode = 128
            return b"", b"fatal: repository not found"

        def kill(self):
            self.returncode = -9

    async def fake_subprocess(*_args, **_kwargs):
        return FailedProcess()

    monkeypatch.setattr(github_module.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(github_module.asyncio, "create_subprocess_exec", fake_subprocess)
    ref = parse_github_repository_url("https://github.com/openai/missing")
    assert ref is not None
    with pytest.raises(GitHubRepositoryError, match="repository not found"):
        await clone_and_render_repository(
            ref,
            timeout_s=30,
            max_repository_bytes=10_000_000,
            max_files=20,
            max_file_bytes=100_000,
            max_chars=100_000,
        )
    assert created and all(not path.exists() for path in created)


@pytest.mark.asyncio
async def test_timed_out_clone_kills_git_and_removes_temporary_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    created = _track_temp_directories(monkeypatch, tmp_path)
    stopped = asyncio.Event()

    class BlockingProcess:
        returncode = None
        killed = False

        async def communicate(self):
            await stopped.wait()
            return b"", b""

        def kill(self):
            self.killed = True
            self.returncode = -9
            stopped.set()

    process = BlockingProcess()

    async def fake_subprocess(*_args, **_kwargs):
        return process

    monkeypatch.setattr(github_module.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(github_module.asyncio, "create_subprocess_exec", fake_subprocess)
    ref = parse_github_repository_url("https://github.com/openai/codex")
    assert ref is not None
    with pytest.raises(GitHubRepositoryError, match="timed out"):
        await clone_and_render_repository(
            ref,
            timeout_s=0.01,
            max_repository_bytes=10_000_000,
            max_files=20,
            max_file_bytes=100_000,
            max_chars=100_000,
        )
    assert process.killed is True
    assert created and all(not path.exists() for path in created)


@pytest.mark.asyncio
async def test_cancelled_clone_kills_git_and_removes_temporary_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    created = _track_temp_directories(monkeypatch, tmp_path)
    started = asyncio.Event()
    stopped = asyncio.Event()

    class BlockingProcess:
        returncode = None
        killed = False

        async def communicate(self):
            started.set()
            await stopped.wait()
            return b"", b""

        def kill(self):
            self.killed = True
            self.returncode = -9
            stopped.set()

    process = BlockingProcess()

    async def fake_subprocess(*_args, **_kwargs):
        return process

    monkeypatch.setattr(github_module.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(github_module.asyncio, "create_subprocess_exec", fake_subprocess)
    ref = parse_github_repository_url("https://github.com/openai/codex")
    assert ref is not None
    task = asyncio.create_task(
        clone_and_render_repository(
            ref,
            timeout_s=30,
            max_repository_bytes=10_000_000,
            max_files=20,
            max_file_bytes=100_000,
            max_chars=100_000,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed is True
    assert created and all(not path.exists() for path in created)


@pytest.mark.asyncio
async def test_acquisition_uses_repository_snapshot_before_direct(
    monkeypatch: pytest.MonkeyPatch,
):
    seen: list[str] = []

    async def allow_url(_url: str, _allow_private: bool = False) -> None:
        pass

    async def snapshot(_ref, **_kwargs):
        seen.append("github_repository")
        return RepositorySnapshot(
            markdown="# Repository\n\n" + ("Structured source code and README. " * 30),
            commit="b" * 40,
            included_files=("README.md", "src/app.py"),
            skipped_files=2,
            checkout_bytes=4096,
            truncated=False,
            cleanup_confirmed=True,
        )

    class RepositoryFirstService(AcquisitionService):
        async def _direct(self, url, candidate, tried):
            raise AssertionError("HTML direct fetch must not run after repository success")

    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    monkeypatch.setattr(acquisition_module, "clone_and_render_repository", snapshot)
    async with httpx.AsyncClient() as client:
        document = await RepositoryFirstService(Settings(_env_file=None), client).acquire(
            _candidate("https://github.com/openai/codex/blob/main/README.md")
        )

    assert document.success
    assert document.acquisition_method == "github_repository"
    assert document.parser_id == "github_repository_structured"
    assert document.final_url == "https://github.com/openai/codex"
    assert document.strategies_tried == ["github_repository"]
    assert document.parse_provenance["cleanup_confirmed"] is True
    assert seen == ["github_repository"]
    assert ACQUISITION_STRATEGY_ORDER[0] == "github_repository"


@pytest.mark.asyncio
async def test_clone_failure_falls_back_to_direct(monkeypatch: pytest.MonkeyPatch):
    async def allow_url(_url: str, _allow_private: bool = False) -> None:
        pass

    async def failed_snapshot(_ref, **_kwargs):
        raise GitHubRepositoryError("clone failed")

    class DirectFallbackService(AcquisitionService):
        async def _direct(self, url, candidate, tried):
            tried.append("direct")
            return self._document(
                candidate,
                "# GitHub HTML fallback\n\n" + ("Rendered repository page. " * 30),
                "direct",
                tried,
                "text/html",
                final_url=url,
            )

    monkeypatch.setattr(acquisition_module, "validate_public_url", allow_url)
    monkeypatch.setattr(acquisition_module, "clone_and_render_repository", failed_snapshot)
    async with httpx.AsyncClient() as client:
        document = await DirectFallbackService(Settings(_env_file=None), client).acquire(
            _candidate()
        )

    assert document.success
    assert document.acquisition_method == "direct"
    assert document.strategies_tried == ["github_repository", "direct"]
