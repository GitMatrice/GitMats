"""
Tests for Workspace Manager.

Tests workspace lifecycle operations:
- Creation (with Git and non-Git originals)
- Destruction
- Locking/unlocking
- Statistics calculation
- Validation
"""

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from gitmats.config import GitMatsConfig
from gitmats.models import (
    Workspace,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceType,
    GitMode,
    FileStatus,
    OperationType,
)
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.workspace import WorkspaceManager


# ===== Fixtures =====

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def temp_config(temp_dir: Path) -> GitMatsConfig:
    """Create a temporary GitMats config."""
    config = GitMatsConfig()
    config.default_workspace_dir = str(temp_dir / "gitmats" / "workspaces")
    config.registry_db = str(temp_dir / "gitmats" / "registry.db")
    return config


@pytest.fixture
def storage_manager(temp_config: GitMatsConfig) -> StorageManager:
    """Create a storage manager with temp config."""
    return StorageManager(temp_config)


@pytest.fixture
def metadata_manager(storage_manager: StorageManager) -> MetadataManager:
    """Create a metadata manager."""
    return MetadataManager(storage_manager.registry_db)


@pytest.fixture
def workspace_manager(
    temp_config: GitMatsConfig,
    storage_manager: StorageManager,
    metadata_manager: MetadataManager,
) -> WorkspaceManager:
    """Create a workspace manager."""
    return WorkspaceManager(
        config=temp_config,
        storage_manager=storage_manager,
        metadata_manager=metadata_manager,
    )


@pytest.fixture
def git_original(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a sample Git repository as original."""
    repo_dir = temp_dir / "git_repo"
    repo_dir.mkdir()
    
    # Initialize Git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        capture_output=True,
    )
    
    # Create some files
    (repo_dir / "file1.txt").write_text("Hello World")
    (repo_dir / "file2.txt").write_text("Another file")
    (repo_dir / "subdir").mkdir()
    (repo_dir / "subdir" / "nested.txt").write_text("Nested file")
    
    # Commit
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        capture_output=True,
    )
    
    yield repo_dir


@pytest.fixture
def non_git_original(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a sample non-Git directory as original."""
    repo_dir = temp_dir / "non_git_dir"
    repo_dir.mkdir()
    
    # Create some files
    (repo_dir / "file1.txt").write_text("Hello World")
    (repo_dir / "file2.txt").write_text("Another file")
    (repo_dir / "subdir").mkdir()
    (repo_dir / "subdir" / "nested.txt").write_text("Nested file")
    
    yield repo_dir


# ===== Validation Tests =====

class TestWorkspaceValidation:
    """Tests for workspace validation."""
    
    def test_validate_workspace_id_valid(self, workspace_manager: WorkspaceManager):
        """Test valid workspace IDs."""
        assert workspace_manager.validate_workspace_id("workspace1")
        assert workspace_manager.validate_workspace_id("my-workspace")
        assert workspace_manager.validate_workspace_id("test_123")
        assert workspace_manager.validate_workspace_id("abc")
    
    def test_validate_workspace_id_invalid(self, workspace_manager: WorkspaceManager):
        """Test invalid workspace IDs."""
        assert not workspace_manager.validate_workspace_id("")
        assert not workspace_manager.validate_workspace_id("workspace with spaces")
        assert not workspace_manager.validate_workspace_id("workspace@special")
        assert not workspace_manager.validate_workspace_id("a" * 65)  # Too long
        assert not workspace_manager.validate_workspace_id("-workspace")  # Starts with hyphen
    
    def test_validate_original_path_valid(self, workspace_manager: WorkspaceManager, non_git_original: Path):
        """Test valid original path."""
        assert workspace_manager.validate_original_path(str(non_git_original))
    
    def test_validate_original_path_invalid(self, workspace_manager: WorkspaceManager):
        """Test invalid original path."""
        assert not workspace_manager.validate_original_path("/nonexistent/path")
        assert not workspace_manager.validate_original_path(__file__)  # File, not dir
    
    def test_check_workspace_exists_false(self, workspace_manager: WorkspaceManager):
        """Test workspace existence check when not exists."""
        assert not workspace_manager.check_workspace_exists("nonexistent")


# ===== Creation Tests =====

class TestWorkspaceCreation:
    """Tests for workspace creation."""
    
    def test_create_workspace_git_original(
        self,
        workspace_manager: WorkspaceManager,
        git_original: Path,
    ):
        """Test creating workspace from Git original."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-git",
            original_path=str(git_original),
        )
        
        assert workspace.workspace_id == "test-git"
        assert workspace.workspace_type == WorkspaceType.INHERITED
        assert workspace.git_mode == GitMode.INHERITED
        assert workspace.status == WorkspaceStatus.ACTIVE
        assert Path(workspace.original_path).resolve() == git_original.resolve()
        assert Path(workspace.workspace_dir).exists()
        assert Path(workspace.copies_dir).exists()
        
        # Check symlinks created
        workspace_dir = Path(workspace.workspace_dir)
        assert (workspace_dir / "file1.txt").is_symlink()
        assert (workspace_dir / "file2.txt").is_symlink()
        assert (workspace_dir / "subdir" / "nested.txt").is_symlink()
    
    def test_create_workspace_non_git_original(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test creating workspace from non-Git original."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-non-git",
            original_path=str(non_git_original),
        )
        
        assert workspace.workspace_id == "test-non-git"
        assert workspace.workspace_type == WorkspaceType.STANDALONE
        assert workspace.git_mode == GitMode.STANDALONE
        assert workspace.status == WorkspaceStatus.ACTIVE
        assert Path(workspace.original_path).resolve() == non_git_original.resolve()
        
        # Check symlinks created
        workspace_dir = Path(workspace.workspace_dir)
        assert (workspace_dir / "file1.txt").is_symlink()
        assert (workspace_dir / "file2.txt").is_symlink()
    
    def test_create_workspace_with_config(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test creating workspace with custom config."""
        config = WorkspaceConfig(
            auto_commit=True,
            commit_prefix="[workspace]",
            sync_on_destroy=True,
            lock_after_create=True,
        )
        
        workspace = workspace_manager.create_workspace(
            workspace_id="test-config",
            original_path=str(non_git_original),
            workspace_config=config,
        )
        
        assert workspace.config.auto_commit == True
        assert workspace.config.commit_prefix == "[workspace]"
        assert workspace.config.sync_on_destroy == True
        # Locked after create
        assert workspace.status == WorkspaceStatus.LOCKED
    
    def test_create_workspace_with_branch(
        self,
        workspace_manager: WorkspaceManager,
        git_original: Path,
    ):
        """Test creating workspace with custom branch name."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-branch",
            original_path=str(git_original),
            branch_name="custom-branch",
        )
        
        assert workspace.git_branch == "custom-branch"
    
    def test_create_workspace_duplicate_id(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test creating workspace with duplicate ID."""
        workspace_manager.create_workspace(
            workspace_id="test-duplicate",
            original_path=str(non_git_original),
        )
        
        with pytest.raises(ValueError, match="already exists"):
            workspace_manager.create_workspace(
                workspace_id="test-duplicate",
                original_path=str(non_git_original),
            )
    
    def test_create_workspace_invalid_id(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test creating workspace with invalid ID."""
        with pytest.raises(ValueError, match="Invalid workspace ID"):
            workspace_manager.create_workspace(
                workspace_id="invalid@id",
                original_path=str(non_git_original),
            )
    
    def test_create_workspace_invalid_path(
        self,
        workspace_manager: WorkspaceManager,
    ):
        """Test creating workspace with invalid path."""
        with pytest.raises(ValueError, match="does not exist"):
            workspace_manager.create_workspace(
                workspace_id="test-invalid-path",
                original_path="/nonexistent",
            )


# ===== Destruction Tests =====

class TestWorkspaceDestruction:
    """Tests for workspace destruction."""
    
    def test_destroy_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test destroying workspace."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-destroy",
            original_path=str(non_git_original),
        )
        
        workspace_dir = Path(workspace.workspace_dir)
        assert workspace_dir.exists()
        
        result = workspace_manager.destroy_workspace("test-destroy")
        assert result == True
        
        # Check workspace marked as destroyed
        destroyed = workspace_manager.get_workspace("test-destroy")
        assert destroyed is not None
        assert destroyed.status == WorkspaceStatus.DESTROYED
        
        # Check directory removed
        assert not workspace_dir.exists()
    
    def test_destroy_workspace_locked(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test destroying locked workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-locked-destroy",
            original_path=str(non_git_original),
        )
        
        workspace_manager.lock_workspace("test-locked-destroy")
        
        # Should fail without force
        with pytest.raises(ValueError, match="is locked"):
            workspace_manager.destroy_workspace("test-locked-destroy")
        
        # Should succeed with force
        result = workspace_manager.destroy_workspace("test-locked-destroy", force=True)
        assert result == True
    
    def test_destroy_workspace_nonexistent(
        self,
        workspace_manager: WorkspaceManager,
    ):
        """Test destroying nonexistent workspace."""
        with pytest.raises(ValueError, match="not found"):
            workspace_manager.destroy_workspace("nonexistent")
    
    def test_destroy_workspace_already_destroyed(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test destroying already destroyed workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-already-destroyed",
            original_path=str(non_git_original),
        )
        
        workspace_manager.destroy_workspace("test-already-destroyed")
        
        with pytest.raises(ValueError, match="already destroyed"):
            workspace_manager.destroy_workspace("test-already-destroyed")


# ===== Lock/Unlock Tests =====

class TestWorkspaceLocking:
    """Tests for workspace locking."""
    
    def test_lock_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test locking workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-lock",
            original_path=str(non_git_original),
        )
        
        result = workspace_manager.lock_workspace("test-lock")
        assert result == True
        
        workspace = workspace_manager.get_workspace("test-lock")
        assert workspace is not None
        assert workspace.status == WorkspaceStatus.LOCKED
    
    def test_unlock_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test unlocking workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-unlock",
            original_path=str(non_git_original),
        )
        
        workspace_manager.lock_workspace("test-unlock")
        result = workspace_manager.unlock_workspace("test-unlock")
        assert result == True
        
        workspace = workspace_manager.get_workspace("test-unlock")
        assert workspace is not None
        assert workspace.status == WorkspaceStatus.ACTIVE
    
    def test_lock_already_locked(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test locking already locked workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-already-locked",
            original_path=str(non_git_original),
        )
        
        workspace_manager.lock_workspace("test-already-locked")
        result = workspace_manager.lock_workspace("test-already-locked")
        assert result == True  # No error, stays locked
    
    def test_lock_destroyed_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test locking destroyed workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-lock-destroyed",
            original_path=str(non_git_original),
        )
        
        workspace_manager.destroy_workspace("test-lock-destroyed")
        
        with pytest.raises(ValueError, match="is destroyed"):
            workspace_manager.lock_workspace("test-lock-destroyed")
    
    def test_unlock_destroyed_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test unlocking destroyed workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-unlock-destroyed",
            original_path=str(non_git_original),
        )
        
        workspace_manager.destroy_workspace("test-unlock-destroyed")
        
        with pytest.raises(ValueError, match="is destroyed"):
            workspace_manager.unlock_workspace("test-unlock-destroyed")


# ===== Statistics Tests =====

class TestWorkspaceStatistics:
    """Tests for workspace statistics."""
    
    def test_update_statistics(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test updating workspace statistics."""
        workspace_manager.create_workspace(
            workspace_id="test-stats",
            original_path=str(non_git_original),
        )
        
        stats = workspace_manager.update_statistics("test-stats")
        
        assert stats["total_files"] == 3  # file1.txt, file2.txt, subdir/nested.txt
        assert stats["linked_files"] == 3
        assert stats["copied_files"] == 0
        assert stats["new_files"] == 0
        assert stats["deleted_files"] == 0
        assert stats["disk_usage_bytes"] == 0
        assert stats["original_size_bytes"] > 0
        assert stats["savings_ratio"] == 1.0  # No copies, 100% savings
    
    def test_statistics_after_modification(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test statistics after file modification."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-stats-mod",
            original_path=str(non_git_original),
        )
        
        # Modify a file (trigger copy-up)
        workspace_file = Path(workspace.workspace_dir) / "file1.txt"
        workspace_file.unlink()  # Remove symlink
        workspace_file.write_text("Modified content")
        
        # Trigger copy-up
        workspace_manager.cow_engine.copy_up("test-stats-mod", "file1.txt")
        
        stats = workspace_manager.update_statistics("test-stats-mod")
        
        assert stats["copied_files"] >= 1
        assert stats["disk_usage_bytes"] > 0
        assert stats["savings_ratio"] < 1.0


# ===== Validation Tests =====

class TestWorkspaceIntegrityValidation:
    """Tests for workspace integrity validation."""
    
    def test_validate_valid_workspace(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test validating a valid workspace."""
        workspace_manager.create_workspace(
            workspace_id="test-validate-valid",
            original_path=str(non_git_original),
        )
        
        result = workspace_manager.validate_workspace("test-validate-valid")
        
        assert result["valid"] == True
        assert len(result["errors"]) == 0
        assert result["file_count"] == 3
    
    def test_validate_nonexistent_workspace(
        self,
        workspace_manager: WorkspaceManager,
    ):
        """Test validating nonexistent workspace."""
        result = workspace_manager.validate_workspace("nonexistent")
        
        assert result["valid"] == False
        assert "not found" in result["error"]
    
    def test_validate_broken_symlink(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test validating workspace with broken symlink."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-validate-broken",
            original_path=str(non_git_original),
        )
        
        # Remove original file
        (non_git_original / "file1.txt").unlink()
        
        result = workspace_manager.validate_workspace("test-validate-broken")
        
        assert result["valid"] == False
        assert any("broken symlink" in e for e in result["errors"])


# ===== List Tests =====

class TestWorkspaceListing:
    """Tests for workspace listing."""
    
    def test_list_workspaces_empty(self, workspace_manager: WorkspaceManager):
        """Test listing when no workspaces."""
        workspaces = workspace_manager.list_workspaces()
        assert len(workspaces) == 0
    
    def test_list_workspaces(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test listing workspaces."""
        workspace_manager.create_workspace(
            workspace_id="test-list-1",
            original_path=str(non_git_original),
        )
        workspace_manager.create_workspace(
            workspace_id="test-list-2",
            original_path=str(non_git_original),
        )
        
        workspaces = workspace_manager.list_workspaces()
        assert len(workspaces) == 2
    
    def test_list_workspaces_filter_status(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test listing workspaces filtered by status."""
        workspace_manager.create_workspace(
            workspace_id="test-list-active",
            original_path=str(non_git_original),
        )
        workspace_manager.create_workspace(
            workspace_id="test-list-destroyed",
            original_path=str(non_git_original),
        )
        workspace_manager.destroy_workspace("test-list-destroyed")
        
        active = workspace_manager.list_workspaces(status=WorkspaceStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].workspace_id == "test-list-active"
        
        destroyed = workspace_manager.list_workspaces(status=WorkspaceStatus.DESTROYED)
        assert len(destroyed) == 1
        assert destroyed[0].workspace_id == "test-list-destroyed"


# ===== Prune Tests =====

class TestWorkspacePruning:
    """Tests for workspace pruning."""
    
    def test_prune_destroyed_workspaces(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test pruning destroyed workspaces."""
        workspace_manager.create_workspace(
            workspace_id="test-prune-active",
            original_path=str(non_git_original),
        )
        workspace_manager.create_workspace(
            workspace_id="test-prune-destroyed",
            original_path=str(non_git_original),
        )
        workspace_manager.destroy_workspace("test-prune-destroyed")
        
        pruned = workspace_manager.prune_workspaces()
        assert "test-prune-destroyed" in pruned
        
        # Active workspace should still exist
        assert workspace_manager.get_workspace("test-prune-active") is not None
        
        # Destroyed workspace should be removed from metadata
        assert workspace_manager.get_workspace("test-prune-destroyed") is None


# ===== File State Tests =====

class TestWorkspaceFileStates:
    """Tests for file state retrieval."""
    
    def test_get_file_states(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test getting file states."""
        workspace_manager.create_workspace(
            workspace_id="test-file-states",
            original_path=str(non_git_original),
        )
        
        states = workspace_manager.get_file_states("test-file-states")
        assert len(states) == 3
        
        # All should be linked initially
        for state in states:
            assert state.status == FileStatus.LINKED
    
    def test_get_file_states_filter_status(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test getting file states filtered by status."""
        workspace = workspace_manager.create_workspace(
            workspace_id="test-file-states-filter",
            original_path=str(non_git_original),
        )
        
        # Modify a file
        workspace_file = Path(workspace.workspace_dir) / "file1.txt"
        workspace_file.unlink()
        workspace_file.write_text("Modified")
        workspace_manager.cow_engine.copy_up("test-file-states-filter", "file1.txt")
        
        linked = workspace_manager.get_file_states(
            "test-file-states-filter",
            status=FileStatus.LINKED,
        )
        assert len(linked) == 2
        
        copied = workspace_manager.get_file_states(
            "test-file-states-filter",
            status=FileStatus.COPIED,
        )
        assert len(copied) == 1
        assert copied[0].relative_path == "file1.txt"


# ===== macOS Path Resolution Tests =====

class TestMacOSPathResolution:
    """Tests for macOS symlink path resolution."""
    
    def test_workspace_original_path_resolution(
        self,
        workspace_manager: WorkspaceManager,
        non_git_original: Path,
    ):
        """Test that original path is resolved correctly."""
        # Create workspace
        workspace = workspace_manager.create_workspace(
            workspace_id="test-path-resolution",
            original_path=str(non_git_original),
        )
        
        # Check path is resolved (handles /var -> /private/var)
        original_resolved = Path(workspace.original_path).resolve()
        assert original_resolved == non_git_original.resolve()
        
        # Check symlinks resolve correctly
        workspace_dir = Path(workspace.workspace_dir)
        symlink_file = workspace_dir / "file1.txt"
        
        assert symlink_file.is_symlink()
        target = symlink_file.resolve()
        assert target == (non_git_original / "file1.txt").resolve()