"""
GitMats versioning backends.

Provides different versioning strategies:
- NullBackend: No versioning (ephemeral workspaces)
- LocalGitBackend: Local Git repository versioning
- LakeBaseBackend: LakeBase API versioning
"""

from gitmats.backends.interface import (
    VersioningBackend,
    BranchResult,
    CommitResult,
    VersionInfo,
    DiffResult,
    RestoreResult,
    DeleteResult,
    FileChange,
)
from gitmats.backends.null import NullBackend
from gitmats.backends.lakebase_client import LakeBaseClient, LakeBaseConfig, LakeBaseError
from gitmats.backends.lakebase import LakeBaseBackend

__all__ = [
    "VersioningBackend",
    "BranchResult",
    "CommitResult",
    "VersionInfo",
    "DiffResult",
    "RestoreResult",
    "DeleteResult",
    "FileChange",
    "NullBackend",
    "LakeBaseClient",
    "LakeBaseConfig",
    "LakeBaseError",
    "LakeBaseBackend",
]