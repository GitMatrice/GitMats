"""Tests for GitMats storage management."""

from pathlib import Path
import tempfile

import pytest

from gitmats.config import GitMatsConfig
from gitmats.storage import StorageManager
from gitmats.models import WorkspaceType, GitMode


class TestStorageManager:
    """Tests for StorageManager."""
    
    def test_init(self, temp_gitmats_root):
        """Test storage manager initialization."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        config.registry_db = str(temp_gitmats_root / "registry.db")
        
        manager = StorageManager(config)
        
        assert manager.workspaces_dir == Path(config.default_workspace_dir)
    
    def test_ensure_root_structure(self, temp_gitmats_root):
        """Test creating root directory structure."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        config.registry_db = str(temp_gitmats_root / "registry.db")
        
        manager = StorageManager(config)
        manager.ensure_root_structure()
        
        assert manager.root_dir.exists()
        assert manager.workspaces_dir.exists()
    
    def test_create_workspace_structure(self, temp_gitmats_root):
        """Test creating workspace directory structure."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        config.registry_db = str(temp_gitmats_root / "registry.db")
        
        manager = StorageManager(config)
        manager.ensure_root_structure()
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-123",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            assert workspace.workspace_id == "test-123"
            assert Path(workspace.storage_path).exists()
            assert Path(workspace.workspace_dir).exists()
            assert Path(workspace.git_dir).exists()
            assert Path(workspace.copies_dir).exists()
    
    def test_destroy_workspace_structure(self, temp_gitmats_root):
        """Test destroying workspace structure."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        config.registry_db = str(temp_gitmats_root / "registry.db")
        
        manager = StorageManager(config)
        manager.ensure_root_structure()
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-destroy",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            storage_path = Path(workspace.storage_path)
            assert storage_path.exists()
            
            manager.destroy_workspace_structure("test-destroy")
            assert not storage_path.exists()
    
    def test_get_workspace_storage_path(self, temp_gitmats_root):
        """Test getting workspace storage path."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        path = manager.get_workspace_storage_path("my-workspace")
        assert str(path).endswith("my-workspace")
    
    def test_validate_workspace_id(self, temp_gitmats_root):
        """Test workspace ID validation."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        # Valid IDs
        assert manager.validate_workspace_id("test-123")
        assert manager.validate_workspace_id("my_workspace")
        assert manager.validate_workspace_id("workspace")
        
        # Invalid IDs
        assert not manager.validate_workspace_id("")
        assert not manager.validate_workspace_id("-test")
        assert not manager.validate_workspace_id("test@123")
        assert not manager.validate_workspace_id("a" * 100)  # Too long
    
    def test_workspace_exists(self, temp_gitmats_root):
        """Test checking if workspace exists."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        manager.ensure_root_structure()
        
        assert not manager.workspace_exists("nonexistent")
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-exists",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            assert manager.workspace_exists("test-exists")
    
    def test_resolve_path(self, temp_gitmats_root):
        """Test resolving path within workspace."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-path",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            resolved = manager.resolve_path(workspace, "src/main.py")
            assert str(resolved).endswith("workspace/src/main.py")
    
    def test_get_cow_path(self, temp_gitmats_root):
        """Test getting COW path."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-cow",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            cow_path = manager.get_cow_path(workspace, "src/main.py")
            assert str(cow_path).endswith("copies/src/main.py")
    
    def test_get_original_path(self, temp_gitmats_root):
        """Test getting original path."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-original",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            original_path = manager.get_original_path(workspace, "src/main.py")
            # On macOS, temp paths may be symlinked from /var to /private/var
            assert Path(original_dir).resolve() in original_path.parents or str(original_path).startswith(original_dir)
    
    def test_calculate_disk_usage(self, temp_gitmats_root):
        """Test calculating disk usage."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        with tempfile.TemporaryDirectory() as original_dir:
            workspace = manager.create_workspace_structure(
                workspace_id="test-disk",
                original_path=original_dir,
                workspace_type=WorkspaceType.STANDALONE,
                git_mode=GitMode.STANDALONE,
            )
            
            # Create a file in copies
            copies_dir = Path(workspace.copies_dir)
            copies_dir.mkdir(parents=True, exist_ok=True)
            test_file = copies_dir / "test.txt"
            test_file.write_text("test content")
            
            usage = manager.calculate_disk_usage(workspace)
            assert usage >= len("test content")
    
    def test_calculate_original_size(self, temp_gitmats_root):
        """Test calculating original directory size."""
        config = GitMatsConfig()
        config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
        
        manager = StorageManager(config)
        
        with tempfile.TemporaryDirectory() as original_dir:
            original = Path(original_dir)
            
            # Create some files
            (original / "file1.txt").write_text("content1")
            (original / "file2.txt").write_text("content2")
            
            size = manager.calculate_original_size(original_dir)
            assert size >= len("content1") + len("content2")