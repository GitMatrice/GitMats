"""
Workspace manager for GitMats.

Orchestrates the complete lifecycle of virtual workspaces:
- Creation (COW + Git setup)
- Destruction (cleanup)
- Statistics and monitoring
- Locking/unlocking
"""

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from gitmats.config import GitMatsConfig
from gitmats.models import (
    Workspace,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceType,
    GitMode,
    FileStatus,
    OperationLog,
    OperationType,
)
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.cow.engine import COWEngine
from gitmats.git.backend import LocalGitBackend


class WorkspaceManager:
    """
    Workspace lifecycle manager.
    
    Coordinates:
    - StorageManager for directory structure
    - MetadataManager for state tracking
    - COWEngine for file management
    - LocalGitBackend for version control
    """
    
    # Workspace ID pattern: alphanumeric, hyphens, underscores
    # Cannot start with hyphen (reserved)
    WORKSPACE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$')
    
    def __init__(
        self,
        config: Optional[GitMatsConfig] = None,
        storage_manager: Optional[StorageManager] = None,
        metadata_manager: Optional[MetadataManager] = None,
    ):
        """
        Initialize workspace manager.
        
        Args:
            config: GitMats configuration.
            storage_manager: Storage manager (created if None).
            metadata_manager: Metadata manager (created if None).
        """
        self.config = config or GitMatsConfig()
        self.storage_manager = storage_manager or StorageManager(self.config)
        self.metadata_manager = metadata_manager or MetadataManager(
            self.storage_manager.registry_db
        )
        self.cow_engine = COWEngine(self.storage_manager, self.metadata_manager)
        self.git_backend = LocalGitBackend(
            self.storage_manager, self.metadata_manager, self.config
        )
    
    def validate_workspace_id(self, workspace_id: str) -> bool:
        """
        Validate workspace ID format.
        
        Args:
            workspace_id: Proposed workspace ID.
        
        Returns:
            True if valid.
        """
        return bool(self.WORKSPACE_ID_PATTERN.match(workspace_id))
    
    def validate_original_path(self, original_path: str) -> bool:
        """
        Validate original directory path.
        
        Args:
            original_path: Path to original directory.
        
        Returns:
            True if valid and exists.
        """
        path = Path(original_path)
        return path.exists() and path.is_dir()
    
    def check_workspace_exists(self, workspace_id: str) -> bool:
        """
        Check if workspace already exists.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            True if workspace exists.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        return workspace is not None and workspace.status != WorkspaceStatus.DESTROYED
    
    def create_workspace(
        self,
        workspace_id: str,
        original_path: str,
        branch_name: Optional[str] = None,
        workspace_config: Optional[WorkspaceConfig] = None,
        created_by: Optional[str] = None,
    ) -> Workspace:
        """
        Create a new virtual workspace.
        
        Steps:
        1. Validate inputs
        2. Detect workspace type
        3. Create directory structure
        4. Initialize metadata
        5. Create COW symlinks
        6. Setup Git (if applicable)
        7. Calculate initial statistics
        
        Args:
            workspace_id: Unique workspace identifier.
            original_path: Path to original directory.
            branch_name: Optional Git branch name (inherited mode).
            workspace_config: Optional per-workspace configuration.
            created_by: Optional creator identifier.
        
        Returns:
            Created Workspace object.
        
        Raises:
            ValueError: If validation fails.
        """
        # Validate workspace ID
        if not self.validate_workspace_id(workspace_id):
            raise ValueError(
                f"Invalid workspace ID '{workspace_id}'. "
                "Must be 1-64 chars, alphanumeric, hyphens, underscores."
            )
        
        # Check for duplicate
        if self.check_workspace_exists(workspace_id):
            raise ValueError(f"Workspace '{workspace_id}' already exists")
        
        # Validate original path
        if not self.validate_original_path(original_path):
            raise ValueError(f"Original path '{original_path}' does not exist or is not a directory")
        
        # Resolve original path (handle macOS /var -> /private/var)
        original_path = str(Path(original_path).resolve())
        
        # Detect workspace type
        workspace_type = self.git_backend.detect_workspace_type(original_path)
        git_mode = GitMode.INHERITED if workspace_type == WorkspaceType.INHERITED else GitMode.STANDALONE
        
        # Create directory structure (returns a Workspace object)
        workspace = self.storage_manager.create_workspace_structure(
            workspace_id=workspace_id,
            original_path=original_path,
            workspace_type=workspace_type,
            git_mode=git_mode,
        )
        
        # Apply configuration
        if workspace_config:
            workspace.config = workspace_config
        if created_by:
            workspace.created_by = created_by
        
        # Register workspace in metadata
        self.metadata_manager.create_workspace(workspace)
        
        # Setup Git BEFORE COW symlinks (worktree requires empty directory)
        git_success = self.git_backend.setup_git(workspace, branch_name)
        if not git_success:
            # Clean up the created structure before raising
            self.storage_manager.destroy_workspace_structure(workspace_id)
            self.metadata_manager.delete_workspace(workspace_id)
            raise RuntimeError(
                f"Failed to setup Git for workspace '{workspace_id}'. "
                f"Git mode: {git_mode.value}, Original: {original_path}"
            )
        
        # Create COW symlinks for all files
        self.cow_engine.initialize_workspace_links(workspace_id, original_path)
        
        # Calculate initial statistics
        self.update_statistics(workspace_id)
        
        # Log operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.CREATE_WORKSPACE,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
            details_json=f'{{"original_path": "{original_path}", "type": "{workspace_type.value}"}}',
        ))
        
        # Lock if configured
        if workspace.config.lock_after_create:
            self.lock_workspace(workspace_id)
        
        # Return updated workspace
        result = self.metadata_manager.get_workspace(workspace_id)
        if not result:
            raise RuntimeError(f"Failed to retrieve workspace {workspace_id}")
        return result
    
    def destroy_workspace(
        self,
        workspace_id: str,
        force: bool = False,
        sync: bool = False,
    ) -> bool:
        """
        Destroy a workspace.
        
        Steps:
        1. Validate workspace exists
        2. Check if locked (unless force)
        3. Sync to original (if requested)
        4. Cleanup Git
        5. Cleanup COW copies
        6. Remove directory structure
        7. Update metadata status
        
        Args:
            workspace_id: Workspace identifier.
            force: Force destruction even if locked.
            sync: Sync changes to original before destruction.
        
        Returns:
            True if destruction succeeded.
        
        Raises:
            ValueError: If workspace not found or locked.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")
        
        if workspace.status == WorkspaceStatus.DESTROYED:
            raise ValueError(f"Workspace '{workspace_id}' already destroyed")
        
        if workspace.status == WorkspaceStatus.LOCKED and not force:
            raise ValueError(f"Workspace '{workspace_id}' is locked. Use force=True to destroy.")
        
        # Sync if requested and configured
        if sync or workspace.config.sync_on_destroy:
            self._sync_to_original(workspace)
        
        # Cleanup Git
        self.git_backend.cleanup_git(workspace)
        
        # Cleanup COW copies
        self._cleanup_cow(workspace)
        
        # Log operation BEFORE removing database
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.DESTROY_WORKSPACE,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
            details_json=f'{{"sync": {sync}, "force": {force}}}',
        ))
        
        # Remove workspace directory structure
        self.storage_manager.destroy_workspace_structure(workspace_id)
        
        # Update status
        workspace.status = WorkspaceStatus.DESTROYED
        self.metadata_manager.update_workspace(workspace)
        
        return True
    
    def _sync_to_original(self, workspace: Workspace) -> bool:
        """
        Sync workspace changes to original.
        
        This is a placeholder for future implementation.
        Currently just logs the intent.
        
        Args:
            workspace: Workspace to sync.
        
        Returns:
            True if sync succeeded.
        """
        # TODO: Implement actual sync logic
        # For now, just log the operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace.workspace_id,
            operation_type=OperationType.GIT_SYNC,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
            details_json='{"status": "skipped_not_implemented"}',
        ))
        return True
    
    def _cleanup_cow(self, workspace: Workspace) -> None:
        """
        Cleanup COW copies for workspace.
        
        Args:
            workspace: Workspace to cleanup.
        """
        copies_dir = Path(workspace.copies_dir)
        
        # Remove all COW copies
        if copies_dir.exists():
            for cow_file in copies_dir.rglob("*"):
                if cow_file.is_file():
                    cow_file.unlink()
            
            # Remove empty directories
            for cow_dir in sorted(copies_dir.rglob("*"), reverse=True):
                if cow_dir.is_dir() and not any(cow_dir.iterdir()):
                    cow_dir.rmdir()
    
    def lock_workspace(self, workspace_id: str) -> bool:
        """
        Lock a workspace to prevent modifications.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            True if lock succeeded.
        
        Raises:
            ValueError: If workspace not found or already locked/destroyed.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")
        
        if workspace.status == WorkspaceStatus.DESTROYED:
            raise ValueError(f"Workspace '{workspace_id}' is destroyed")
        
        if workspace.status == WorkspaceStatus.LOCKED:
            return True  # Already locked
        
        workspace.status = WorkspaceStatus.LOCKED
        self.metadata_manager.update_workspace(workspace)
        
        # Log operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.LOCK_WORKSPACE,
            relative_path=None,
            timestamp=datetime.now(),
            success=True,
        ))
        
        return True
    
    def unlock_workspace(self, workspace_id: str) -> bool:
        """
        Unlock a workspace to allow modifications.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            True if unlock succeeded.
        
        Raises:
            ValueError: If workspace not found or destroyed.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace '{workspace_id}' not found")
        
        if workspace.status == WorkspaceStatus.DESTROYED:
            raise ValueError(f"Workspace '{workspace_id}' is destroyed")
        
        if workspace.status != WorkspaceStatus.LOCKED:
            return True  # Not locked
        
        workspace.status = WorkspaceStatus.ACTIVE
        self.metadata_manager.update_workspace(workspace)
        
        return True
    
    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """
        Get workspace by ID.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Workspace object, or None if not found.
        """
        return self.metadata_manager.get_workspace(workspace_id)
    
    def list_workspaces(
        self,
        status: Optional[WorkspaceStatus] = None,
        original_path: Optional[str] = None,
    ) -> list[Workspace]:
        """
        List workspaces.
        
        Args:
            status: Filter by status.
            original_path: Filter by original path.
        
        Returns:
            List of Workspace objects.
        """
        return self.metadata_manager.list_workspaces(status, original_path)
    
    def update_statistics(self, workspace_id: str) -> dict:
        """
        Calculate and update workspace statistics.
        
        Statistics:
        - Total files count
        - Linked files count
        - Copied files count
        - New files count
        - Deleted files count
        - Disk usage (bytes)
        - Savings ratio
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Statistics dictionary.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return {}
        
        # First, sync COW state to detect any new/modified files
        self.cow_engine.sync_cow_state(workspace_id)
        
        # Scan file states
        file_states = self.metadata_manager.list_file_states(workspace_id)
        
        total_files = len(file_states)
        linked_files = sum(1 for s in file_states if s.status == FileStatus.LINKED)
        copied_files = sum(1 for s in file_states if s.status == FileStatus.COPIED)
        new_files = sum(1 for s in file_states if s.status == FileStatus.NEW)
        deleted_files = sum(1 for s in file_states if s.status == FileStatus.DELETED)
        
        # Calculate disk usage (COW copies + new files)
        disk_usage = self.storage_manager.calculate_disk_usage(workspace)
        
        # Calculate original size (for savings ratio)
        original_size = self.storage_manager.calculate_original_size(workspace.original_path)
        
        # Calculate savings ratio
        savings_ratio = 0.0
        if original_size > 0:
            savings_ratio = 1.0 - (disk_usage / original_size)
        
        # Update workspace statistics in memory
        workspace.total_files = total_files
        workspace.linked_files = linked_files
        workspace.copied_files = copied_files
        workspace.new_files = new_files
        workspace.deleted_files = deleted_files
        workspace.disk_usage_bytes = disk_usage
        
        self.metadata_manager.update_workspace(workspace)
        
        # Update stats table
        self.metadata_manager.update_workspace_stats(
            workspace_id=workspace_id,
            total_files=total_files,
            linked_files=linked_files,
            copied_files=copied_files,
            new_files=new_files,
            deleted_files=deleted_files,
            disk_usage_bytes=disk_usage,
            original_size_bytes=original_size,
        )
        
        return {
            "total_files": total_files,
            "linked_files": linked_files,
            "copied_files": copied_files,
            "new_files": new_files,
            "deleted_files": deleted_files,
            "disk_usage_bytes": disk_usage,
            "original_size_bytes": original_size,
            "savings_ratio": savings_ratio,
        }
    
    def get_file_states(
        self,
        workspace_id: str,
        status: Optional[FileStatus] = None,
    ) -> list:
        """
        Get file states for workspace.
        
        Args:
            workspace_id: Workspace identifier.
            status: Filter by status.
        
        Returns:
            List of FileState objects.
        """
        return self.metadata_manager.list_file_states(workspace_id, status)
    
    def validate_workspace(self, workspace_id: str) -> dict:
        """
        Validate workspace integrity.
        
        Checks:
        - All symlinks resolve correctly
        - COW copies exist for copied files
        - Metadata matches actual files
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Validation report dictionary.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return {"valid": False, "error": "Workspace not found"}
        
        errors = []
        warnings = []
        
        workspace_dir = Path(workspace.workspace_dir)
        copies_dir = Path(workspace.copies_dir)
        
        # Check directory existence
        if not workspace_dir.exists():
            errors.append("Workspace directory does not exist")
        
        if not copies_dir.exists():
            warnings.append("COW copies directory does not exist")
        
        # Check file states
        file_states = self.metadata_manager.list_file_states(workspace_id)
        
        for state in file_states:
            rel_path = state.relative_path
            workspace_file = workspace_dir / rel_path
            
            if state.status == FileStatus.LINKED:
                # Check symlink
                if not workspace_file.is_symlink():
                    errors.append(f"{rel_path}: expected symlink, got regular file")
                else:
                    target = workspace_file.resolve()
                    if not target.exists():
                        errors.append(f"{rel_path}: broken symlink")
            
            elif state.status == FileStatus.COPIED:
                # Check symlink to COW
                if not workspace_file.is_symlink():
                    # Could be regular file (directly edited)
                    warnings.append(f"{rel_path}: regular file instead of symlink to COW")
                
                # Check COW copy exists
                if state.cow_path:
                    cow_file = Path(state.cow_path)
                    if not cow_file.exists():
                        errors.append(f"{rel_path}: COW copy missing")
            
            elif state.status == FileStatus.NEW:
                # Check file exists
                if not workspace_file.exists():
                    errors.append(f"{rel_path}: new file missing")
            
            elif state.status == FileStatus.DELETED:
                # Check file doesn't exist
                if workspace_file.exists() or workspace_file.is_symlink():
                    warnings.append(f"{rel_path}: deleted file still exists")
        
        # Log validation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.VALIDATE,
            relative_path=None,
            timestamp=datetime.now(),
            success=len(errors) == 0,
            error_message="\n".join(errors) if errors else None,
            details_json=f'{{"errors": {len(errors)}, "warnings": {len(warnings)}}}',
        ))
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "file_count": len(file_states),
        }
    
    def prune_workspaces(
        self,
        max_age_days: Optional[int] = None,
        status: Optional[WorkspaceStatus] = None,
    ) -> list[str]:
        """
        Prune old or destroyed workspaces.
        
        Args:
            max_age_days: Maximum age in days (destroy destroyed workspaces older than this).
            status: Filter by status (default: DESTROYED).
        
        Returns:
            List of pruned workspace IDs.
        """
        status_filter = status or WorkspaceStatus.DESTROYED
        
        workspaces = self.list_workspaces(status=status_filter)
        pruned = []
        
        cutoff_time = None
        if max_age_days:
            cutoff_time = datetime.now().timestamp() - (max_age_days * 24 * 3600)
        
        for workspace in workspaces:
            # Check age if specified
            if cutoff_time and workspace.created_at.timestamp() > cutoff_time:
                continue
            
            # Remove metadata entry
            self.metadata_manager.delete_workspace(workspace.workspace_id)
            pruned.append(workspace.workspace_id)
        
        return pruned