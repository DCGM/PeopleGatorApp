from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import subprocess

try:
    from people_gator_api._version import (
        GENERATED_PACKAGE_VERSION as _generated_package_version,
        GENERATED_GIT_COMMIT as _generated_git_commit,
        GENERATED_GIT_DIRTY as _generated_git_dirty,
    )
except ImportError:
    _generated_package_version: str | None = None
    _generated_git_commit: str | None = None
    _generated_git_dirty: bool | None = None


@dataclass(frozen=True, slots=True)
class VersionInfo:
    package_version: str
    git_commit: str | None
    git_dirty: bool

    @property
    def full_version(self) -> str:
        """Package version, optionally suffixed with the git commit and dirty flag."""
        if self.git_commit is None:
            return self.package_version
        suffix = f"+{self.git_commit}"
        if self.git_dirty:
            suffix += ".dirty"
        return f"{self.package_version}{suffix}"


def _run_git(*args: str, repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


@lru_cache(maxsize=1)
def get_version_info(package_name: str = "people-gator-api") -> VersionInfo:
    """Return the package version plus the current or generated git state."""
    if _generated_package_version is not None:
        return VersionInfo(
            package_version=_generated_package_version,
            git_commit=_generated_git_commit,
            git_dirty=_generated_git_dirty is True,
        )

    try:
        package_version = version(package_name)
    except PackageNotFoundError:
        package_version = "0.0.0+unknown"

    repo_root = Path(__file__).resolve().parents[3]
    git_commit = _run_git("rev-parse", "--short", "HEAD", repo_root=repo_root)
    git_dirty = False
    if git_commit is not None:
        status = _run_git("status", "--porcelain", repo_root=repo_root)
        git_dirty = bool(status)

    return VersionInfo(
        package_version=package_version,
        git_commit=git_commit,
        git_dirty=git_dirty,
    )
