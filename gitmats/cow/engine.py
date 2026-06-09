"""
Copy-on-Write engine for GitMats.

Manages:
- Symlink creation for workspace files
- Copy-up operations when files are modified
- File state tracking
- Modification detection
"""

import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from gitmats.models import FileState, FileStatus, OperationLog, OperationType
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager


class COWEngine:
    """
    Copy-on-Write engine for virtual workspace files.
    
    Key responsibilities:
    1. Create symlinks pointing to original files (linked state)
    2. Detect modifications via symlink resolution
    3. Copy modified files to COW storage (copy-up)
    4. Track file states throughout lifecycle
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        metadata_manager: MetadataManager,
    ):
        """
        Initialize COW engine.
        
        Args:
            storage_manager: Storage manager for path resolution.
            metadata_manager: Metadata manager for state tracking.
        """
        self.storage_manager = storage_manager
        self.metadata_manager = metadata_manager
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of file contents.
        
        Args:
            file_path: Path to file.
        
        Returns:
            SHA256 hash string.
        """
        sha256_hash = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        
        return sha256_hash.hexdigest()
    
    def create_linked_file(
        self,
        workspace_id: str,
        rel_path: str,
        original_path: Path,
    ) -> FileState:
        """
        Create symlink pointing to original file.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path within workspace.
            original_path: Path to original file.
        
        Returns:
            FileState for the linked file.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")
        
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        
        # Create parent directories in workspace
        workspace_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create symlink pointing to original
        if workspace_file.exists() or workspace_file.is_symlink():
            workspace_file.unlink()
        
        workspace_file.symlink_to(original_path)
        
        # Record state
        original_hash = self.calculate_file_hash(original_path)
        original_size = original_path.stat().st_size
        original_mtime = datetime.fromtimestamp(original_path.stat().st_mtime)
        
        self.metadata_manager.record_linked_file(
            workspace_id=workspace_id,
            rel_path=rel_path,
            original_hash=original_hash,
            original_size=original_size,
            original_mtime=original_mtime,
        )
        
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        if not state:
            raise RuntimeError(f"Failed to create state for {rel_path}")
        return state
    
    def initialize_workspace_links(
        self,
        workspace_id: str,
        original_path: str,
    ) -> dict[str, FileState]:
        """
        Initialize all file links for a workspace.
        
        Scans original directory and creates symlinks for all files
        (excluding .git directory).
        
        Args:
            workspace_id: Workspace identifier.
            original_path: Path to original directory.
        
        Returns:
            Dictionary mapping relative paths to FileStates.
        """
        original = Path(original_path)
        states = {}
        
        # Excluded directories and patterns (should not be tracked)
        EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", 
                         "node_modules", ".idea", ".vscode"}
        
        for file_path in original.rglob("*"):
            # Skip excluded directories
            if any(p.name in EXCLUDED_DIRS for p in file_path.parents):
                continue
            
            # Skip .egg-info directories and files
            if file_path.name.endswith(".egg-info") or any(p.name.endswith(".egg-info") for p in file_path.parents):
                continue
            
            if file_path.is_file():
                rel_path = str(file_path.relative_to(original))
                
                state = self.create_linked_file(
                    workspace_id=workspace_id,
                    rel_path=rel_path,
                    original_path=file_path,
                )
                states[rel_path] = state
        
        return states
    
    def detect_modification(self, workspace_id: str, rel_path: str) -> bool:
        """
        Detect if a file has been modified.
        
        Modification detection:
        1. If symlink, compare current hash with original hash
        2. If regular file, it's already copied (modified)
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            True if file is modified, False otherwise.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return False
        
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        if not state:
            # File not tracked - treat as potential modification
            return True
        
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        
        if not workspace_file.exists():
            # File deleted in workspace
            return state.status != FileStatus.DELETED
        
        if workspace_file.is_symlink():
            # Still symlink - check if original changed or symlink broken
            try:
                target = workspace_file.resolve()
                current_hash = self.calculate_file_hash(target)
                return current_hash != state.original_hash
            except OSError:
                # Symlink target missing - file modified (deleted original)
                return True
        
        # Regular file in workspace - already copied (modified)
        return True
    
    def copy_up(self, workspace_id: str, rel_path: str) -> Optional[FileState]:
        """
        Perform copy-up operation.
        
        Copies file from original to COW storage and updates symlink
        to point to the copy.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            Updated FileState, or None if copy-up not needed.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")
        
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        
        if not workspace_file.exists():
            # File doesn't exist in workspace
            return None
        
        # Check if already copied
        if state and state.status == FileStatus.COPIED:
            # Already copied - check if further modified
            cow_path = Path(state.cow_path)
            current_hash = self.calculate_file_hash(workspace_file)
            
            if cow_path.exists():
                cow_hash = self.calculate_file_hash(cow_path)
                if current_hash == cow_hash:
                    # No new modification
                    return state
            
            # Update COW copy
            cow_file = self.storage_manager.get_cow_path(workspace, rel_path)
            cow_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace_file, cow_file)
            
            return self._update_cow_state(workspace_id, rel_path, cow_file)
        
        # Check if linked
        if workspace_file.is_symlink():
            # Check if this is a NEW file already symlinked to COW copy
            if state and state.status == FileStatus.NEW:
                # Already tracked as NEW - nothing to do
                return state
            
            # Get original info
            original_target = workspace_file.resolve()
            original_hash = state.original_hash if state else self.calculate_file_hash(original_target)
            original_size = state.original_size if state else original_target.stat().st_size
            
            # Create COW copy
            cow_file = self.storage_manager.get_cow_path(workspace, rel_path)
            cow_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy from symlink target to COW
            shutil.copy2(original_target, cow_file)
            
            # Remove symlink and create new symlink to COW copy
            workspace_file.unlink()
            workspace_file.symlink_to(cow_file)
            
            # Record copy-up
            self.metadata_manager.record_copy_up(
                workspace_id=workspace_id,
                rel_path=rel_path,
                original_hash=original_hash,
                original_size=original_size,
                cow_path=str(cow_file),
                cow_hash=self.calculate_file_hash(cow_file),
                cow_size=cow_file.stat().st_size,
                cow_mtime=datetime.fromtimestamp(cow_file.stat().st_mtime),
            )
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace_id,
                operation_type=OperationType.COPY_UP,
                relative_path=rel_path,
                timestamp=datetime.now(),
                success=True,
            ))
            
            return self.metadata_manager.get_file_state(workspace_id, rel_path)
        
        # Regular file in workspace
        # Check if it was a linked file that was modified (symlink replaced)
        if state and state.status == FileStatus.LINKED:
            # Linked file was modified - treat as copy-up
            original_hash = state.original_hash
            original_size = state.original_size
            
            # Create COW copy from the modified file
            cow_file = self.storage_manager.get_cow_path(workspace, rel_path)
            cow_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(workspace_file, cow_file)
            
            # Create symlink to COW copy
            workspace_file.unlink()
            workspace_file.symlink_to(cow_file)
            
            # Record copy-up
            self.metadata_manager.record_copy_up(
                workspace_id=workspace_id,
                rel_path=rel_path,
                original_hash=original_hash,
                original_size=original_size,
                cow_path=str(cow_file),
                cow_hash=self.calculate_file_hash(cow_file),
                cow_size=cow_file.stat().st_size,
                cow_mtime=datetime.fromtimestamp(cow_file.stat().st_mtime),
            )
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace_id,
                operation_type=OperationType.COPY_UP,
                relative_path=rel_path,
                timestamp=datetime.now(),
                success=True,
            ))
            
            return self.metadata_manager.get_file_state(workspace_id, rel_path)
        
        # Truly new file (no existing state)
        cow_file = self.storage_manager.get_cow_path(workspace, rel_path)
        cow_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if workspace file is already symlinked to COW copy
        if workspace_file.is_symlink():
            target = workspace_file.resolve()
            copies_dir = Path(workspace.copies_dir).resolve()
            
            # Check if symlink already points to copies directory
            if copies_dir in target.parents or target.parent.resolve() == copies_dir:
                # Already correctly symlinked - verify COW copy exists
                if target.exists():
                    # Just return existing state or create metadata if missing
                    if not state:
                        self.metadata_manager.record_new_file(
                            workspace_id=workspace_id,
                            rel_path=rel_path,
                            cow_path=str(target),
                            cow_hash=self.calculate_file_hash(target),
                            cow_size=target.stat().st_size,
                        )
                    return self.metadata_manager.get_file_state(workspace_id, rel_path)
        
        # Copy workspace file to COW storage (resolve symlink if needed)
        source_file = workspace_file.resolve() if workspace_file.is_symlink() else workspace_file
        if source_file != cow_file:
            shutil.copy2(source_file, cow_file)
        
        # Replace workspace file with symlink to COW copy
        if workspace_file.exists() or workspace_file.is_symlink():
            workspace_file.unlink()
        workspace_file.symlink_to(cow_file)
        
        self.metadata_manager.record_new_file(
            workspace_id=workspace_id,
            rel_path=rel_path,
            cow_path=str(cow_file),
            cow_hash=self.calculate_file_hash(cow_file),
            cow_size=cow_file.stat().st_size,
        )
        
        # Log operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.COPY_UP,
            relative_path=rel_path,
            timestamp=datetime.now(),
            success=True,
        ))
        
        return self.metadata_manager.get_file_state(workspace_id, rel_path)
    
    def _update_cow_state(
        self,
        workspace_id: str,
        rel_path: str,
        cow_file: Path,
    ) -> FileState:
        """Update state for existing COW file."""
        # Re-record with new info
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        if state:
            orig_hash = state.original_hash or ""
            orig_size = state.original_size or 0
            self.metadata_manager.record_copy_up(
                workspace_id=workspace_id,
                rel_path=rel_path,
                original_hash=orig_hash,
                original_size=orig_size,
                cow_path=str(cow_file),
                cow_hash=self.calculate_file_hash(cow_file),
                cow_size=cow_file.stat().st_size,
                cow_mtime=datetime.fromtimestamp(cow_file.stat().st_mtime),
            )
        
        result = self.metadata_manager.get_file_state(workspace_id, rel_path)
        if not result:
            raise RuntimeError(f"Failed to update state for {rel_path}")
        return result
    
    def reset_file(self, workspace_id: str, rel_path: str) -> Optional[FileState]:
        """
        Reset file to original state.
        
        Removes COW copy and recreates symlink to original.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            Updated FileState, or None if file doesn't exist.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")
        
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        if not state:
            return None
        
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        original_file = self.storage_manager.get_original_path(workspace, rel_path)
        
        # Remove existing file/symlink in workspace
        if workspace_file.exists() or workspace_file.is_symlink():
            workspace_file.unlink()
        
        # Remove COW copy if exists
        if state.cow_path:
            cow_file = Path(state.cow_path)
            if cow_file.exists():
                cow_file.unlink()
        
        # Recreate symlink to original
        if original_file.exists():
            workspace_file.parent.mkdir(parents=True, exist_ok=True)
            workspace_file.symlink_to(original_file)
            
            # Re-record as linked
            self.metadata_manager.record_linked_file(
                workspace_id=workspace_id,
                rel_path=rel_path,
                original_hash=self.calculate_file_hash(original_file),
                original_size=original_file.stat().st_size,
                original_mtime=datetime.fromtimestamp(original_file.stat().st_mtime),
            )
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace_id,
                operation_type=OperationType.RESET_FILE,
                relative_path=rel_path,
                timestamp=datetime.now(),
                success=True,
            ))
            
            state = self.metadata_manager.get_file_state(workspace_id, rel_path)
            return state
        
        return None
    
    def delete_file(self, workspace_id: str, rel_path: str) -> bool:
        """
        Delete file from workspace.
        
        Removes symlink/file and marks as deleted in state.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            True if deletion succeeded.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return False
        
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        
        # Remove file/symlink
        if workspace_file.exists() or workspace_file.is_symlink():
            workspace_file.unlink()
        
        # Record deletion
        self.metadata_manager.record_deletion(workspace_id, rel_path)
        
        # Log operation
        self.metadata_manager.log_operation(OperationLog(
            workspace_id=workspace_id,
            operation_type=OperationType.DELETE_FILE,
            relative_path=rel_path,
            timestamp=datetime.now(),
            success=True,
        ))
        
        return True
    
    def get_file_status(self, workspace_id: str, rel_path: str) -> FileStatus:
        """
        Get current status of a file.
        
        Args:
            workspace_id: Workspace identifier.
            rel_path: Relative path of file.
        
        Returns:
            Current FileStatus.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return FileStatus.UNKNOWN
        
        state = self.metadata_manager.get_file_state(workspace_id, rel_path)
        workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
        
        # File doesn't exist
        if not workspace_file.exists() and not workspace_file.is_symlink():
            if state:
                return FileStatus.DELETED
            return FileStatus.UNKNOWN
        
        # Check if symlink
        if workspace_file.is_symlink():
            target = workspace_file.resolve()
            
            if state:
                # Check state.status first to distinguish NEW from COPIED
                if state.status == FileStatus.NEW:
                    return FileStatus.NEW
                
                cow_dir = Path(workspace.copies_dir).resolve()
                target_parent = target.parent.resolve() if target.parent.exists() else target.parent
                
                # Check if symlink points to COW directory
                if cow_dir in target.parents or target_parent == cow_dir or cow_dir == target.parent:
                    return FileStatus.COPIED
                return FileStatus.LINKED
            
            # No state - check by path
            cow_dir = Path(workspace.copies_dir).resolve()
            if cow_dir in target.parents:
                return FileStatus.COPIED
            return FileStatus.LINKED
        
        # Regular file - check if tracked
        if state:
            if state.status == FileStatus.NEW:
                return FileStatus.NEW
            return FileStatus.COPIED
        
        # Untracked regular file
        return FileStatus.NEW
    
    def scan_workspace_files(
        self,
        workspace_id: str,
        detect_modifications: bool = True,
    ) -> dict[str, FileStatus]:
        """
        Scan all files in workspace and report status.
        
        Args:
            workspace_id: Workspace identifier.
            detect_modifications: Whether to detect modifications.
        
        Returns:
            Dictionary mapping relative paths to FileStatus.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return {}
        
        workspace_dir = Path(workspace.workspace_dir)
        statuses = {}
        
        # Get all tracked files
        tracked_states = self.metadata_manager.list_file_states(workspace_id)
        tracked_paths = {s.relative_path for s in tracked_states}
        
        # Scan workspace directory
        # Excluded directories and patterns (should not be tracked)
        EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", 
                         "node_modules", ".idea", ".vscode", "*.egg-info"}
        
        for file_path in workspace_dir.rglob("*"):
            # Skip excluded directories
            if any(p.name in EXCLUDED_DIRS or p.name.endswith(".egg-info") for p in file_path.parents):
                continue
            if file_path.name in EXCLUDED_DIRS or file_path.name.endswith(".egg-info"):
                continue
            
            if file_path.is_file() or file_path.is_symlink():
                rel_path = str(file_path.relative_to(workspace_dir))
                
                if detect_modifications:
                    # Check for modification
                    if file_path.is_symlink() and self.detect_modification(workspace_id, rel_path):
                        statuses[rel_path] = FileStatus.COPIED
                    else:
                        statuses[rel_path] = self.get_file_status(workspace_id, rel_path)
                else:
                    statuses[rel_path] = self.get_file_status(workspace_id, rel_path)
        
        # Check for deleted files
        for rel_path in tracked_paths:
            if rel_path not in statuses:
                statuses[rel_path] = FileStatus.DELETED
        
        return statuses
    
    def sync_modifications(self, workspace_id: str) -> list[str]:
        """
        Perform copy-up for all modified and new files.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            List of paths that were copied.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return []
        
        copied_files = []
        statuses = self.scan_workspace_files(workspace_id, detect_modifications=True)
        
        for rel_path, status in statuses.items():
            if status == FileStatus.COPIED:
                # Check if needs copy-up
                workspace_file = self.storage_manager.resolve_path(workspace, rel_path)
                
                if workspace_file.is_symlink():
                    # Symlink to original modified - copy-up needed
                    self.copy_up(workspace_id, rel_path)
                    copied_files.append(rel_path)
                else:
                    # Regular file - might need COW sync
                    state = self.metadata_manager.get_file_state(workspace_id, rel_path)
                    if state and state.status == FileStatus.LINKED:
                        self.copy_up(workspace_id, rel_path)
                        copied_files.append(rel_path)
            elif status == FileStatus.NEW:
                # New file - perform copy-up to track it
                self.copy_up(workspace_id, rel_path)
                copied_files.append(rel_path)
        
        return copied_files
    
    def sync_cow_state(self, workspace_id: str) -> dict[str, FileStatus]:
        """
        Sync all COW state for workspace.
        
        Scans workspace for modifications and new files, performs copy-up
        for all untracked changes, and updates metadata.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Dictionary of paths and their final status after sync.
        """
        workspace = self.metadata_manager.get_workspace(workspace_id)
        if not workspace:
            return {}
        
        # Perform copy-up for all modified and new files
        copied_files = self.sync_modifications(workspace_id)
        
        # Get final statuses
        final_statuses = {}
        for rel_path in copied_files:
            final_statuses[rel_path] = self.get_file_status(workspace_id, rel_path)
        
        return final_statuses