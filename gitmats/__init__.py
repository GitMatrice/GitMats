"""
GitMats - Git Materialized Virtual Workspace

Provides isolated virtual workspaces with:
- Zero disk overhead on creation (symlink-based)
- Copy-on-write semantics for modifications
- Full Git integration for version control
- Read-only original workspace protection
"""

__version__ = "0.1.0"
__author__ = "GitMats Team"

from gitmats.models import (
    Workspace,
    FileState,
    WorkspaceConfig,
    GitCommit,
    OperationLog,
    WorkspaceType,
    WorkspaceStatus,
    GitMode,
    FileStatus,
    CommitType,
    OperationType,
)
from gitmats.config import GitMatsConfig, load_config
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager

__all__ = [
    # Version info
    "__version__",
    "__author__",
    # Data models
    "Workspace",
    "FileState",
    "WorkspaceConfig",
    "GitCommit",
    "OperationLog",
    "WorkspaceType",
    "WorkspaceStatus",
    "GitMode",
    "FileStatus",
    "CommitType",
    "OperationType",
    # Configuration
    "GitMatsConfig",
    "load_config",
    # Managers
    "MetadataManager",
    "StorageManager",
]