"""
Versioning Backend Interface for GitMats.

Defines abstract interface for different versioning strategies:
- LocalGitBackend: Uses Git worktree + alternates
- LakeBaseBackend: Delegates to LakeBase API for branch/version management
- NullBackend: No versioning, only COW file tracking
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class BranchResult:
    """Result of creating a workspace branch."""
    branch_id: Optional[str] = None
    connection_uri: Optional[str] = None
    status: str = "unknown"
    message: Optional[str] = None


@dataclass
class CommitResult:
    """Result of creating a commit/version."""
    version_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    lsn: Optional[str] = None  # LakeBase LSN for database commits
    commit_sha: Optional[str] = None  # Git SHA for local commits
    status: str = "unknown"
    message: Optional[str] = None


@dataclass
class VersionInfo:
    """Information about a version/commit."""
    version_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    lsn: Optional[str] = None
    commit_sha: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    message: Optional[str] = None


@dataclass
class DiffResult:
    """Result of comparing two versions."""
    source_id: str
    target_id: str
    files_changed: list[str] = field(default_factory=list)
    schema_diff: Optional[dict] = None
    data_diff: Optional[dict] = None
    summary: Optional[str] = None


@dataclass
class RestoreResult:
    """Result of restoring to a version."""
    version_id: str
    new_timeline_id: Optional[str] = None
    backup_branch_id: Optional[str] = None
    status: str = "unknown"
    message: Optional[str] = None


@dataclass
class DeleteResult:
    """Result of deleting a branch."""
    status: str = "unknown"
    message: Optional[str] = None


@dataclass
class FileChange:
    """Represents a file change for commit."""
    path: str
    change_type: str  # "add", "modify", "delete"
    content: Optional[str] = None  # For new/modified files
    size: Optional[int] = None
    hash: Optional[str] = None


class VersioningBackend(ABC):
    """
    Abstract interface for versioning backends.
    
    GitMats supports multiple versioning strategies:
    - Local Git (default): Uses Git worktree + alternates
    - LakeBase: Delegates to LakeBase API for branch/version management
    - Null: No versioning, only COW file tracking
    """
    
    @abstractmethod
    def create_workspace_branch(self, workspace) -> BranchResult:
        """
        Create a version control branch for the workspace.
        
        Args:
            workspace: Workspace object.
        
        Returns:
            BranchResult with branch_id, connection_uri, status.
        """
        pass
    
    @abstractmethod
    def commit(
        self,
        workspace,
        message: str,
        files: Optional[list[FileChange]] = None,
        author: Optional[str] = None,
    ) -> CommitResult:
        """
        Create a commit/version snapshot.
        
        Args:
            workspace: Target workspace.
            message: Commit message.
            files: List of file changes (path, content, change_type).
            author: Author string.
        
        Returns:
            CommitResult with version_id, timestamp, status.
        """
        pass
    
    @abstractmethod
    def list_versions(self, workspace, limit: int = 10) -> list[VersionInfo]:
        """
        List all versions/commits for workspace branch.
        
        Args:
            workspace: Workspace to list versions for.
            limit: Maximum number of versions to return.
        
        Returns:
            List of VersionInfo objects.
        """
        pass
    
    @abstractmethod
    def get_version(self, workspace, version_id: str) -> Optional[VersionInfo]:
        """
        Get specific version details.
        
        Args:
            workspace: Workspace the version belongs to.
            version_id: Version identifier.
        
        Returns:
            VersionInfo or None if not found.
        """
        pass
    
    @abstractmethod
    def diff_versions(
        self,
        workspace,
        source_id: str,
        target_id: str,
    ) -> DiffResult:
        """
        Compare two versions.
        
        Args:
            workspace: Workspace to compare versions in.
            source_id: Source version identifier.
            target_id: Target version identifier.
        
        Returns:
            DiffResult with comparison details.
        """
        pass
    
    @abstractmethod
    def restore_version(
        self,
        workspace,
        version_id: str,
    ) -> RestoreResult:
        """
        Restore workspace to a specific version state.
        
        Args:
            workspace: Workspace to restore.
            version_id: Target version identifier.
        
        Returns:
            RestoreResult with restoration details.
        """
        pass
    
    @abstractmethod
    def delete_branch(self, workspace) -> DeleteResult:
        """
        Delete workspace branch on destroy.
        
        Args:
            workspace: Workspace to delete branch for.
        
        Returns:
            DeleteResult with deletion status.
        """
        pass
    
    # Optional methods with default implementations
    
    def get_status(self, workspace) -> dict:
        """
        Get workspace status.
        
        Args:
            workspace: Workspace to check.
        
        Returns:
            Status dictionary.
        """
        return {"backend": self.__class__.__name__}
    
    def sync_to_original(self, workspace) -> bool:
        """
        Sync workspace changes to original.
        
        Args:
            workspace: Workspace to sync.
        
        Returns:
            True if sync successful.
        """
        return False
    
    def install_hooks(self, workspace) -> bool:
        """
        Install version control hooks.
        
        Args:
            workspace: Workspace for hooks.
        
        Returns:
            True if hooks installed.
        """
        return True
    
    def stage_cow_files(self, workspace) -> list[str]:
        """
        Stage COW files for commit.
        
        Args:
            workspace: Workspace to stage.
        
        Returns:
            List of staged file paths.
        """
        return []