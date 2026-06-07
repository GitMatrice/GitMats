"""
Tests for Null Backend.

Tests the no-versioning backend for ephemeral workspaces.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from gitmats.config import GitMatsConfig
from gitmats.models import (
    Workspace,
    WorkspaceStatus,
    WorkspaceType,
    GitMode,
    FileStatus,
)
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.backends.null import NullBackend


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
    """Create a storage manager."""
    return StorageManager(temp_config)


@pytest.fixture
def metadata_manager(storage_manager: StorageManager) -> MetadataManager:
    """Create a metadata manager."""
    return MetadataManager(storage_manager.registry_db)


@pytest.fixture
def null_backend(
    storage_manager: StorageManager,
    metadata_manager: MetadataManager,
) -> NullBackend:
    """Create a null backend."""
    return NullBackend(storage_manager, metadata_manager)


@pytest.fixture
def sample_workspace(
    temp_dir: Path,
    storage_manager: StorageManager,
    metadata_manager: MetadataManager,
) -> Workspace:
    """Create a sample workspace for testing."""
    original_path = temp_dir / "original"
    original_path.mkdir()
    (original_path / "file1.txt").write_text("Hello World")
    
    workspace = storage_manager.create_workspace_structure(
        workspace_id="test-null",
        original_path=str(original_path),
        workspace_type=WorkspaceType.STANDALONE,
        git_mode=GitMode.STANDALONE,
    )
    metadata_manager.create_workspace(workspace)
    
    return workspace


# ===== Setup Tests =====

class TestNullSetup:
    """Tests for null backend setup."""
    
    def test_setup_workspace(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test setting up workspace with null backend."""
        result = null_backend.setup_workspace(sample_workspace)
        
        assert result == True
        
        # Check workspace properties
        workspace = null_backend.metadata_manager.get_workspace("test-null")
        assert workspace is not None
        assert workspace.workspace_type == WorkspaceType.STANDALONE
        assert workspace.git_mode == GitMode.STANDALONE
        assert workspace.git_branch is None
        assert workspace.git_head is None
    
    def test_no_git_directory(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not create Git directory."""
        null_backend.setup_workspace(sample_workspace)
        
        workspace_dir = Path(sample_workspace.workspace_dir)
        git_dir = workspace_dir / ".git"
        
        assert not git_dir.exists()


# ===== Cleanup Tests =====

class TestNullCleanup:
    """Tests for null backend cleanup."""
    
    def test_cleanup_workspace(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test cleaning up workspace with null backend."""
        null_backend.setup_workspace(sample_workspace)
        
        result = null_backend.cleanup_workspace(sample_workspace)
        
        assert result == True
    
    def test_cleanup_no_git_operations(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that cleanup does not perform Git operations."""
        null_backend.setup_workspace(sample_workspace)
        
        # Cleanup should succeed even without Git setup
        result = null_backend.cleanup_workspace(sample_workspace)
        
        assert result == True


# ===== Commit Tests =====

class TestNullCommit:
    """Tests for null backend commit behavior."""
    
    def test_commit_not_supported(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not support commits."""
        null_backend.setup_workspace(sample_workspace)
        
        result = null_backend.commit_changes(
            sample_workspace,
            message="Test commit",
        )
        
        assert result is None


# ===== Branch Tests =====

class TestNullBranch:
    """Tests for null backend branch behavior."""
    
    def test_branch_not_supported(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not support branches."""
        null_backend.setup_workspace(sample_workspace)
        
        result = null_backend.create_branch(
            sample_workspace,
            branch_name="test-branch",
        )
        
        assert result == False


# ===== Status Tests =====

class TestNullStatus:
    """Tests for null backend status."""
    
    def test_get_status_empty(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test getting status for empty workspace."""
        null_backend.setup_workspace(sample_workspace)
        
        status = null_backend.get_status(sample_workspace)
        
        assert status["backend"] == "null"
        assert status["total_files"] == 0
    
    def test_get_status_with_files(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test getting status with tracked files."""
        null_backend.setup_workspace(sample_workspace)
        
        # Record some file states
        null_backend.metadata_manager.record_linked_file(
            workspace_id="test-null",
            rel_path="file1.txt",
            original_hash="abc123",
            original_size=100,
        )
        
        status = null_backend.get_status(sample_workspace)
        
        assert status["backend"] == "null"
        assert status["total_files"] == 1
        assert status["modified"] == 0


# ===== Sync Tests =====

class TestNullSync:
    """Tests for null backend sync behavior."""
    
    def test_sync_not_supported(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not support sync."""
        null_backend.setup_workspace(sample_workspace)
        
        result = null_backend.sync_to_original(sample_workspace)
        
        assert result == False


# ===== Hooks Tests =====

class TestNullHooks:
    """Tests for null backend hooks."""
    
    def test_hooks_not_needed(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not need hooks."""
        result = null_backend.install_hooks(sample_workspace)
        
        assert result == True


# ===== Stage Tests =====

class TestNullStage:
    """Tests for null backend staging."""
    
    def test_stage_not_supported(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
    ):
        """Test that null backend does not stage files."""
        result = null_backend.stage_cow_files(sample_workspace)
        
        assert result == []


# ===== Integration Tests =====

class TestNullIntegration:
    """Integration tests for null backend."""
    
    def test_full_workflow(
        self,
        null_backend: NullBackend,
        sample_workspace: Workspace,
        temp_dir: Path,
    ):
        """Test full workflow with null backend."""
        # Setup
        assert null_backend.setup_workspace(sample_workspace)
        
        # Check workspace
        workspace = null_backend.metadata_manager.get_workspace("test-null")
        assert workspace is not None
        assert workspace.git_mode == GitMode.STANDALONE
        
        # Try unsupported operations
        assert null_backend.commit_changes(sample_workspace, "test") is None
        assert null_backend.create_branch(sample_workspace, "test") == False
        assert null_backend.sync_to_original(sample_workspace) == False
        
        # Cleanup
        assert null_backend.cleanup_workspace(sample_workspace)