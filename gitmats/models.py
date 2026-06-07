"""
Core data models for GitMats.

Defines the fundamental entities: Workspace, FileState, GitCommit, OperationLog.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class WorkspaceType(Enum):
    """Workspace type based on original directory."""
    
    INHERITED = "inherited"  # Original has Git
    STANDALONE = "standalone"  # Original has no Git


class WorkspaceStatus(Enum):
    """Workspace lifecycle status."""
    
    ACTIVE = "active"
    LOCKED = "locked"
    DESTROYED = "destroyed"
    ARCHIVED = "archived"


class GitMode(Enum):
    """Git integration mode."""
    
    INHERITED = "inherited"  # Share Git with original (worktree)
    STANDALONE = "standalone"  # Independent Git repo


class FileStatus(Enum):
    """File state in virtual workspace."""
    
    LINKED = "linked"  # Symlink to original (unchanged)
    COPIED = "copied"  # Symlink to COW copy (modified)
    NEW = "new"  # Created in workspace (no original)
    DELETED = "deleted"  # Removed from workspace
    UNKNOWN = "unknown"  # Not tracked


class CommitType(Enum):
    """Type of commit in workspace."""
    
    USER = "user"  # User-initiated commit
    COW_SYNC = "cow_sync"  # Automatic COW sync
    BASE = "base"  # Virtual base commit (standalone)
    SYNC = "sync"  # Sync to original commit


class OperationType(Enum):
    """Operation types for logging."""
    
    # Workspace operations
    CREATE_WORKSPACE = "create_workspace"
    DESTROY_WORKSPACE = "destroy_workspace"
    LOCK_WORKSPACE = "lock_workspace"
    
    # File operations
    COPY_UP = "copy_up"
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    RESET_FILE = "reset_file"
    
    # Git operations
    GIT_ADD = "git_add"
    GIT_COMMIT = "git_commit"
    GIT_BRANCH = "git_branch"
    GIT_SYNC = "git_sync"
    
    # Metadata operations
    METADATA_UPDATE = "metadata_update"
    VALIDATE = "validate"


@dataclass
class WorkspaceConfig:
    """Per-workspace configuration."""
    
    auto_commit: bool = False
    commit_prefix: str = ""
    sync_on_destroy: bool = False
    lock_after_create: bool = False
    hooks_enabled: bool = True
    max_disk_usage_mb: int = 0


@dataclass
class Workspace:
    """Virtual workspace entity.
    
    A workspace represents an isolated working environment
    that shares files with an original directory via COW.
    """
    
    # Identity
    workspace_id: str
    
    # Paths
    original_path: str
    storage_path: str
    workspace_dir: str
    git_dir: str
    copies_dir: str
    metadata_db: str
    
    # Type
    workspace_type: WorkspaceType
    
    # State
    status: WorkspaceStatus
    created_at: datetime
    last_accessed: Optional[datetime]
    created_by: Optional[str]
    
    # Git Integration
    git_mode: GitMode
    git_branch: Optional[str]
    git_head: Optional[str]
    
    # Statistics (cached)
    total_files: int = 0
    linked_files: int = 0
    copied_files: int = 0
    new_files: int = 0
    deleted_files: int = 0
    disk_usage_bytes: int = 0
    
    # Configuration
    config: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    
    # Backend metadata (for LakeBase)
    backend_meta: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "workspace_id": self.workspace_id,
            "original_path": self.original_path,
            "storage_path": self.storage_path,
            "workspace_dir": self.workspace_dir,
            "git_dir": self.git_dir,
            "copies_dir": self.copies_dir,
            "metadata_db": self.metadata_db,
            "workspace_type": self.workspace_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "created_by": self.created_by,
            "git_mode": self.git_mode.value,
            "git_branch": self.git_branch,
            "git_head": self.git_head,
            "total_files": self.total_files,
            "linked_files": self.linked_files,
            "copied_files": self.copied_files,
            "new_files": self.new_files,
            "deleted_files": self.deleted_files,
            "disk_usage_bytes": self.disk_usage_bytes,
            "config": {
                "auto_commit": self.config.auto_commit,
                "commit_prefix": self.config.commit_prefix,
                "sync_on_destroy": self.config.sync_on_destroy,
                "lock_after_create": self.config.lock_after_create,
                "hooks_enabled": self.config.hooks_enabled,
                "max_disk_usage_mb": self.config.max_disk_usage_mb,
            },
            "backend_meta": self.backend_meta,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Workspace":
        """Create from dictionary."""
        return cls(
            workspace_id=data["workspace_id"],
            original_path=data["original_path"],
            storage_path=data["storage_path"],
            workspace_dir=data["workspace_dir"],
            git_dir=data["git_dir"],
            copies_dir=data["copies_dir"],
            metadata_db=data["metadata_db"],
            workspace_type=WorkspaceType(data["workspace_type"]),
            status=WorkspaceStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]) if data["last_accessed"] else None,
            created_by=data.get("created_by"),
            git_mode=GitMode(data["git_mode"]),
            git_branch=data.get("git_branch"),
            git_head=data.get("git_head"),
            total_files=data.get("total_files", 0),
            linked_files=data.get("linked_files", 0),
            copied_files=data.get("copied_files", 0),
            new_files=data.get("new_files", 0),
            deleted_files=data.get("deleted_files", 0),
            disk_usage_bytes=data.get("disk_usage_bytes", 0),
            config=WorkspaceConfig(**data.get("config", {})),
            backend_meta=data.get("backend_meta", {}),
        )


@dataclass
class FileState:
    """
    State tracking for a file in workspace.
    
    Tracks whether file is:
    - Linked to original (unchanged)
    - Copied to COW layer (modified)
    - New (created in workspace)
    - Deleted (removed from workspace)
    """
    
    # Identity
    workspace_id: str
    relative_path: str
    
    # State
    status: FileStatus
    
    # Original (if linked or copied)
    original_hash: Optional[str] = None
    original_size: Optional[int] = None
    original_mtime: Optional[datetime] = None
    
    # COW Copy (if copied or new)
    cow_path: Optional[str] = None
    cow_hash: Optional[str] = None
    cow_size: Optional[int] = None
    cow_mtime: Optional[datetime] = None
    
    # Modification tracking
    first_modified_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None
    modification_count: int = 0
    
    # Git integration
    git_tracked: bool = True
    git_blob_sha: Optional[str] = None
    git_staged: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "relative_path": self.relative_path,
            "status": self.status.value,
            "original_hash": self.original_hash,
            "original_size": self.original_size,
            "original_mtime": self.original_mtime.isoformat() if self.original_mtime else None,
            "cow_path": self.cow_path,
            "cow_hash": self.cow_hash,
            "cow_size": self.cow_size,
            "cow_mtime": self.cow_mtime.isoformat() if self.cow_mtime else None,
            "first_modified_at": self.first_modified_at.isoformat() if self.first_modified_at else None,
            "last_modified_at": self.last_modified_at.isoformat() if self.last_modified_at else None,
            "modification_count": self.modification_count,
            "git_tracked": self.git_tracked,
            "git_blob_sha": self.git_blob_sha,
            "git_staged": self.git_staged,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FileState":
        """Create from dictionary."""
        return cls(
            workspace_id=data["workspace_id"],
            relative_path=data["relative_path"],
            status=FileStatus(data["status"]),
            original_hash=data.get("original_hash"),
            original_size=data.get("original_size"),
            original_mtime=datetime.fromisoformat(data["original_mtime"]) if data.get("original_mtime") else None,
            cow_path=data.get("cow_path"),
            cow_hash=data.get("cow_hash"),
            cow_size=data.get("cow_size"),
            cow_mtime=datetime.fromisoformat(data["cow_mtime"]) if data.get("cow_mtime") else None,
            first_modified_at=datetime.fromisoformat(data["first_modified_at"]) if data.get("first_modified_at") else None,
            last_modified_at=datetime.fromisoformat(data["last_modified_at"]) if data.get("last_modified_at") else None,
            modification_count=data.get("modification_count", 0),
            git_tracked=data.get("git_tracked", True),
            git_blob_sha=data.get("git_blob_sha"),
            git_staged=data.get("git_staged", False),
        )


@dataclass
class GitCommit:
    """
    Git commit metadata tracked by GitMats.
    
    Links Git commits to workspace state.
    """
    
    # Identity
    workspace_id: str
    commit_sha: str
    
    # Content
    commit_message: str
    tree_sha: Optional[str] = None
    parent_sha: Optional[str] = None
    
    # Author
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    authored_at: Optional[datetime] = None
    
    # Committer
    committer_name: Optional[str] = None
    committer_email: Optional[str] = None
    committed_at: Optional[datetime] = None
    
    # Statistics
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    
    # GitMats metadata
    commit_type: CommitType = CommitType.USER
    metadata_json: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "commit_sha": self.commit_sha,
            "commit_message": self.commit_message,
            "tree_sha": self.tree_sha,
            "parent_sha": self.parent_sha,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "authored_at": self.authored_at.isoformat() if self.authored_at else None,
            "committer_name": self.committer_name,
            "committer_email": self.committer_email,
            "committed_at": self.committed_at.isoformat() if self.committed_at else None,
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "commit_type": self.commit_type.value,
            "metadata_json": self.metadata_json,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "GitCommit":
        """Create from dictionary."""
        return cls(
            workspace_id=data["workspace_id"],
            commit_sha=data["commit_sha"],
            commit_message=data["commit_message"],
            tree_sha=data.get("tree_sha"),
            parent_sha=data.get("parent_sha"),
            author_name=data.get("author_name"),
            author_email=data.get("author_email"),
            authored_at=datetime.fromisoformat(data["authored_at"]) if data.get("authored_at") else None,
            committer_name=data.get("committer_name"),
            committer_email=data.get("committer_email"),
            committed_at=datetime.fromisoformat(data["committed_at"]) if data.get("committed_at") else None,
            files_changed=data.get("files_changed", 0),
            insertions=data.get("insertions", 0),
            deletions=data.get("deletions", 0),
            commit_type=CommitType(data.get("commit_type", "user")),
            metadata_json=data.get("metadata_json"),
        )


@dataclass
class OperationLog:
    """Log of all operations in workspace.
    
    Provides audit trail and debugging info.
    """
    
    # Identity
    workspace_id: str
    operation_type: OperationType
    timestamp: datetime
    
    # Operation
    relative_path: Optional[str] = None
    operation_id: Optional[int] = None
    duration_ms: Optional[int] = None
    
    # Result
    success: bool = True
    error_message: Optional[str] = None
    
    # Details
    details_json: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type.value,
            "relative_path": self.relative_path,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error_message": self.error_message,
            "details_json": self.details_json,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "OperationLog":
        """Create from dictionary."""
        return cls(
            workspace_id=data["workspace_id"],
            operation_id=data.get("operation_id"),
            operation_type=OperationType(data["operation_type"]),
            relative_path=data.get("relative_path"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            duration_ms=data.get("duration_ms"),
            success=data.get("success", True),
            error_message=data.get("error_message"),
            details_json=data.get("details_json"),
        )