"""
Storage management for GitMats.

Handles directory structure creation and path resolution.
"""

from pathlib import Path
from typing import Optional

from gitmats.config import GitMatsConfig
from gitmats.models import Workspace, WorkspaceType, GitMode, WorkspaceStatus, WorkspaceConfig
from datetime import datetime


class StorageManager:
    """
    Manages GitMats directory structure.
    
    Creates and manages:
    - ~/.gitmats/ root directory
    - ~/.gitmats/workspaces/{id}/ workspace storage
    - Per-workspace subdirectories (workspace/, git/, copies/)
    """
    
    def __init__(self, config: Optional[GitMatsConfig] = None):
        """
        Initialize storage manager.
        
        Args:
            config: GitMats configuration. If None, uses default.
        """
        self.config = config or GitMatsConfig()
        self.root_dir = self.config.get_storage_path().parent
        self.workspaces_dir = self.config.get_storage_path()
        self.registry_db = self.config.get_registry_db_path()
    
    def ensure_root_structure(self) -> None:
        """
        Ensure GitMats root directory structure exists.
        
        Creates:
        - ~/.gitmats/
        - ~/.gitmats/workspaces/
        - ~/.gitmats/registry.db
        """
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)
        
        # Registry DB is created by MetadataManager
        self.registry_db.parent.mkdir(parents=True, exist_ok=True)
    
    def get_workspace_storage_path(self, workspace_id: str) -> Path:
        """
        Get storage path for workspace.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Path to workspace storage directory.
        """
        return self.workspaces_dir / workspace_id
    
    def create_workspace_structure(
        self,
        workspace_id: str,
        original_path: str,
        workspace_type: WorkspaceType,
        git_mode: GitMode,
    ) -> Workspace:
        """
        Create workspace directory structure.
        
        Args:
            workspace_id: Unique workspace identifier.
            original_path: Path to original workspace.
            workspace_type: Type of workspace.
            git_mode: Git integration mode.
        
        Returns:
            Workspace object with all paths set.
        """
        storage_path = self.get_workspace_storage_path(workspace_id)
        
        # Create directory structure
        workspace_dir = storage_path / "workspace"
        git_dir = storage_path / "git"
        copies_dir = storage_path / "copies"
        metadata_db = storage_path / "metadata.db"
        
        storage_path.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        git_dir.mkdir(parents=True, exist_ok=True)
        copies_dir.mkdir(parents=True, exist_ok=True)
        
        # Create Git subdirectories
        (git_dir / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (git_dir / "objects" / "pack").mkdir(parents=True, exist_ok=True)
        (git_dir / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (git_dir / "refs" / "gitmats").mkdir(parents=True, exist_ok=True)
        (git_dir / "hooks").mkdir(parents=True, exist_ok=True)
        
        # Create workspace config file
        config_path = storage_path / ".gitmats.yaml"
        config_path.touch()
        
        return Workspace(
            workspace_id=workspace_id,
            original_path=str(Path(original_path).resolve()),
            storage_path=str(storage_path),
            workspace_dir=str(workspace_dir),
            git_dir=str(git_dir),
            copies_dir=str(copies_dir),
            metadata_db=str(metadata_db),
            workspace_type=workspace_type,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=git_mode,
            git_branch=None,
            git_head=None,
            config=WorkspaceConfig(),
        )
    
    def destroy_workspace_structure(self, workspace_id: str) -> None:
        """
        Remove workspace directory structure.
        
        Args:
            workspace_id: Workspace identifier.
        """
        storage_path = self.get_workspace_storage_path(workspace_id)
        
        if storage_path.exists():
            # Remove all contents
            import shutil
            shutil.rmtree(storage_path)
    
    def resolve_path(self, workspace: Workspace, rel_path: str) -> Path:
        """
        Resolve a relative path within workspace.
        
        Args:
            workspace: Workspace object.
            rel_path: Relative path within workspace.
        
        Returns:
            Absolute path in workspace directory.
        """
        return Path(workspace.workspace_dir) / rel_path
    
    def get_cow_path(self, workspace: Workspace, rel_path: str) -> Path:
        """
        Get COW storage path for a file.
        
        Args:
            workspace: Workspace object.
            rel_path: Relative path of file.
        
        Returns:
            Path in COW copies directory.
        """
        return Path(workspace.copies_dir) / rel_path
    
    def get_original_path(self, workspace: Workspace, rel_path: str) -> Path:
        """
        Get original path for a file.
        
        Args:
            workspace: Workspace object.
            rel_path: Relative path of file.
        
        Returns:
            Path in original directory.
        """
        return Path(workspace.original_path) / rel_path
    
    def validate_workspace_id(self, workspace_id: str) -> bool:
        """
        Validate workspace ID format.
        
        Args:
            workspace_id: Proposed workspace ID.
        
        Returns:
            True if valid, False otherwise.
        """
        # Must be non-empty
        if not workspace_id:
            return False
        
        # Must be alphanumeric with hyphens/underscores
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', workspace_id):
            return False
        
        # Must not start with hyphen
        if workspace_id.startswith('-'):
            return False
        
        # Must be reasonable length
        if len(workspace_id) > 64:
            return False
        
        return True
    
    def workspace_exists(self, workspace_id: str) -> bool:
        """
        Check if workspace storage exists.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            True if workspace storage exists.
        """
        storage_path = self.get_workspace_storage_path(workspace_id)
        return storage_path.exists()
    
    def get_workspace_config_path(self, workspace_id: str) -> Path:
        """
        Get workspace config file path.
        
        Args:
            workspace_id: Workspace identifier.
        
        Returns:
            Path to .gitmats.yaml config.
        """
        return self.get_workspace_storage_path(workspace_id) / ".gitmats.yaml"
    
    def calculate_disk_usage(self, workspace: Workspace) -> int:
        """
        Calculate total disk usage for workspace.
        
        Args:
            workspace: Workspace object.
        
        Returns:
            Total bytes used by workspace.
        """
        copies_dir = Path(workspace.copies_dir)
        
        total_bytes = 0
        
        if copies_dir.exists():
            for file in copies_dir.rglob('*'):
                if file.is_file():
                    total_bytes += file.stat().st_size
        
        # Add Git objects size
        git_dir = Path(workspace.git_dir)
        if git_dir.exists():
            for file in git_dir.rglob('*'):
                if file.is_file():
                    total_bytes += file.stat().st_size
        
        return total_bytes
    
    def calculate_original_size(self, original_path: str) -> int:
        """
        Calculate total size of original directory.
        
        Args:
            original_path: Path to original directory.
        
        Returns:
            Total bytes in original directory.
        """
        original = Path(original_path)
        
        total_bytes = 0
        
        if original.exists():
            for file in original.rglob('*'):
                if file.is_file() and not file.name.startswith('.git'):
                    total_bytes += file.stat().st_size
        
        return total_bytes