"""Git integration package."""

from gitmats.git.utils import (
    is_git_repo,
    get_git_root,
    get_git_dir,
    get_current_branch,
    get_current_head,
    init_repo,
    add_worktree,
)
from gitmats.git.backend import LocalGitBackend

__all__ = [
    "is_git_repo",
    "get_git_root",
    "get_git_dir",
    "get_current_branch",
    "get_current_head",
    "init_repo",
    "add_worktree",
    "LocalGitBackend",
]