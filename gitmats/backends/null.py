"""
Null Backend for GitMats.

Provides a no-versioning backend for ephemeral workspaces.
Useful for:
- Temporary workspaces that don't need version history
- Testing and prototyping
- Quick scratchpad workspaces
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from gitmats.models import (
    Workspace,
    WorkspaceType,
    GitMode,
    OperationLog,
    OperationType,
)
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager


class NullBackend:
    """
    No-versioning backend for ephemeral workspaces.
    
    This backend:
    - Does not create Git repositories
    - Does not support commits or branches
    - Tracks changes only in metadata
    - Allows workspace destruction without cleanup
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        metadata_manager: MetadataManager,
    ) -> None:
        """
        Initialize null backend.
        
        Args:
            storage_manager: Storage manager for paths.
            metadata_manager: Metadata manager for tracking.
        """
        self.storage_manager = storage_manager
        self.metadata_manager = metadata_manager
    
    def setup_workspace(self, workspace: Workspace) -> bool:
        """
        Setup workspace without version control.
        
        Args:
            workspace: Workspace to setup.
        
        Returns:
            True if setup successful.
        """
        # Set workspace as standalone with null Git mode
        workspace.workspace_type = WorkspaceType.STANDALONE
        workspace.git_mode = GitMode.STANDALONE
        workspace.git_branch = None
        workspace.git_head = None
        
        # Update workspace in metadata
        self.metadata_manager.update_workspace(workspace)
        
        # Log operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace.workspace_id,
            operation_type=OperationType.CREATE_WORKSPACE,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
            details_json='{"backend": "null"}',
        ))
        
        return True
    
    def cleanup_workspace(self, workspace: Workspace) -> bool:
        """
        Cleanup workspace without version control cleanup.
        
        For null backend, there's no Git cleanup needed.
        
        Args:
            workspace: Workspace to cleanup.
        
        Returns:
            True if cleanup successful.
        """
        # No Git cleanup needed for null backend
        # Just log the cleanup
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace.workspace_id,
            operation_type=OperationType.DESTROY_WORKSPACE,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
            details_json='{"backend": "null"}',
        ))
        
        return True
    
    def commit_changes(
        self,
        workspace: Workspace,
        message: str,
        author: Optional[str] = None,
    ) -> Optional[str]:
        """
        Null backend does not support commits.
        
        Args:
            workspace: Workspace to commit.
            message: Commit message (ignored).
            author: Author string (ignored).
        
        Returns:
            None (no commit created).
        """
        # Null backend does not support commits
        return None
    
    def create_branch(
        self,
        workspace: Workspace,
        branch_name: str,
        start_point: Optional[str] = None,
    ) -> bool:
        """
        Null backend does not support branches.
        
        Args:
            workspace: Workspace for branch.
            branch_name: Branch name (ignored).
            start_point: Starting point (ignored).
        
        Returns:
            False (branches not supported).
        """
        # Null backend does not support branches
        return False
    
    def get_status(self, workspace: Workspace) -> dict:
        """
        Get workspace status.
        
        Args:
            workspace: Workspace to check.
        
        Returns:
            Status dictionary with file information.
        """
        # Get file states from metadata
        states = self.metadata_manager.list_file_states(workspace.workspace_id)
        
        return {
            "backend": "null",
            "total_files": len(states),
            "modified": len([s for s in states if s.status.value == "copied"]),
            "new": len([s for s in states if s.status.value == "new"]),
            "deleted": len([s for s in states if s.status.value == "deleted"]),
        }
    
    def sync_to_original(self, workspace: Workspace) -> bool:
        """
        Null backend does not support sync.
        
        Args:
            workspace: Workspace to sync.
        
        Returns:
            False (sync not supported).
        """
        # Null backend does not support sync
        return False
    
    def install_hooks(self, workspace: Workspace) -> bool:
        """
        Null backend does not install hooks.
        
        Args:
            workspace: Workspace for hooks.
        
        Returns:
            True (no hooks needed).
        """
        # No hooks needed for null backend
        return True
    
    def stage_cow_files(self, workspace: Workspace) -> list[str]:
        """
        Null backend does not stage files.
        
        Args:
            workspace: Workspace to stage.
        
        Returns:
            Empty list (no staging).
        """
        # Null backend does not stage files
        return []