"""Tests for COW engine."""

from datetime import datetime
from pathlib import Path
import tempfile

import pytest

from gitmats.config import GitMatsConfig
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.cow.engine import COWEngine
from gitmats.models import (
    Workspace,
    WorkspaceType,
    WorkspaceStatus,
    GitMode,
    FileStatus,
)


@pytest.fixture
def cow_setup():
    """Create full COW setup for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create GitMats structure
        config = GitMatsConfig()
        config.default_workspace_dir = str(root / "workspaces")
        config.registry_db = str(root / "registry.db")
        
        storage_manager = StorageManager(config)
        storage_manager.ensure_root_structure()
        
        metadata_manager = MetadataManager(config.get_registry_db_path())
        
        # Create original directory with files
        original_dir = root / "original"
        original_dir.mkdir()
        (original_dir / "src").mkdir()
        (original_dir / "src" / "main.py").write_text("print('hello')")
        (original_dir / "src" / "utils.py").write_text("def helper(): pass")
        (original_dir / "config.yaml").write_text("name: test")
        (original_dir / "README.md").write_text("# Test Project")
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-cow",
            original_path=str(original_dir),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        
        metadata_manager.create_workspace(workspace)
        
        # Create COW engine
        cow_engine = COWEngine(storage_manager, metadata_manager)
        
        yield {
            "root": root,
            "original_dir": original_dir,
            "workspace": workspace,
            "storage_manager": storage_manager,
            "metadata_manager": metadata_manager,
            "cow_engine": cow_engine,
        }


class TestCOWEngine:
    """Tests for COW engine."""
    
    def test_calculate_file_hash(self, cow_setup):
        """Test file hash calculation."""
        cow_engine = cow_setup["cow_engine"]
        original_dir = cow_setup["original_dir"]
        
        file_path = original_dir / "README.md"
        hash1 = cow_engine.calculate_file_hash(file_path)
        
        # Same content should give same hash
        hash2 = cow_engine.calculate_file_hash(file_path)
        assert hash1 == hash2
        
        # Different content should give different hash
        file_path.write_text("different content")
        hash3 = cow_engine.calculate_file_hash(file_path)
        assert hash1 != hash3
    
    def test_create_linked_file(self, cow_setup):
        """Test creating linked file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        state = cow_engine.create_linked_file(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
            original_path=original_dir / "src" / "main.py",
        )
        
        assert state.status == FileStatus.LINKED
        assert state.relative_path == "src/main.py"
        assert state.original_hash is not None
        
        # Verify symlink exists
        workspace_file = Path(workspace.workspace_dir) / "src" / "main.py"
        assert workspace_file.is_symlink()
        # On macOS, /var symlinks to /private/var
        assert workspace_file.resolve() == (original_dir / "src" / "main.py").resolve()
    
    def test_initialize_workspace_links(self, cow_setup):
        """Test initializing all workspace links."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        states = cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Should have linked all files
        assert len(states) == 4  # main.py, utils.py, config.yaml, README.md
        
        for state in states.values():
            assert state.status == FileStatus.LINKED
    
    def test_detect_modification_linked(self, cow_setup):
        """Test detecting modification on linked file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Linked file should not show modification
        is_modified = cow_engine.detect_modification(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        assert is_modified is False
    
    def test_detect_modification_after_change(self, cow_setup):
        """Test detecting modification after file change."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify original file
        (original_dir / "src" / "main.py").write_text("print('modified')")
        
        # Should detect modification
        is_modified = cow_engine.detect_modification(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        assert is_modified is True
    
    def test_copy_up_operation(self, cow_setup):
        """Test copy-up operation."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify file through symlink (writes to original)
        original_file = original_dir / "src" / "main.py"
        original_file.write_text("print('modified content')")
        
        # Perform copy-up
        state = cow_engine.copy_up(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        assert state is not None
        assert state.status == FileStatus.COPIED
        assert state.cow_path is not None
        
        # Verify symlink now points to COW copy
        workspace_file = Path(workspace.workspace_dir) / "src" / "main.py"
        assert workspace_file.is_symlink()
        
        cow_path = Path(state.cow_path)
        # Compare resolved paths for macOS compatibility
        assert workspace_file.resolve() == cow_path.resolve()
        assert cow_path.exists()
    
    def test_copy_up_preserves_content(self, cow_setup):
        """Test that copy-up preserves file content."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify original
        new_content = "print('new content')"
        (original_dir / "src" / "main.py").write_text(new_content)
        
        # Copy-up
        cow_engine.copy_up(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        # Verify COW copy has modified content
        workspace_file = Path(workspace.workspace_dir) / "src" / "main.py"
        assert workspace_file.read_text() == new_content
    
    def test_reset_file(self, cow_setup):
        """Test resetting file to original."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify and copy-up
        (original_dir / "src" / "main.py").write_text("modified")
        cow_engine.copy_up(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        # Reset file
        state = cow_engine.reset_file(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        assert state is not None
        assert state.status == FileStatus.LINKED
        
        # Verify symlink points back to original
        workspace_file = Path(workspace.workspace_dir) / "src" / "main.py"
        assert workspace_file.is_symlink()
        # Compare resolved paths for macOS compatibility
        assert workspace_file.resolve() == (original_dir / "src" / "main.py").resolve()
    
    def test_delete_file(self, cow_setup):
        """Test deleting file from workspace."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Delete file
        result = cow_engine.delete_file(
            workspace_id=workspace.workspace_id,
            rel_path="config.yaml",
        )
        
        assert result is True
        
        # Verify file is deleted in workspace
        workspace_file = Path(workspace.workspace_dir) / "config.yaml"
        assert not workspace_file.exists()
        
        # Verify state shows deleted
        state = cow_engine.get_file_status(
            workspace_id=workspace.workspace_id,
            rel_path="config.yaml",
        )
        assert state == FileStatus.DELETED
    
    def test_get_file_status_linked(self, cow_setup):
        """Test getting status of linked file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        status = cow_engine.get_file_status(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        assert status == FileStatus.LINKED
    
    def test_get_file_status_copied(self, cow_setup):
        """Test getting status of copied file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify and copy-up
        (original_dir / "src" / "main.py").write_text("modified")
        cow_engine.copy_up(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        status = cow_engine.get_file_status(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        assert status == FileStatus.COPIED
    
    def test_get_file_status_new(self, cow_setup):
        """Test getting status of new file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        # Create new file in workspace
        workspace_file = Path(workspace.workspace_dir) / "new_file.py"
        workspace_file.write_text("new content")
        
        status = cow_engine.get_file_status(
            workspace_id=workspace.workspace_id,
            rel_path="new_file.py",
        )
        
        assert status == FileStatus.NEW
    
    def test_scan_workspace_files(self, cow_setup):
        """Test scanning all files in workspace."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        statuses = cow_engine.scan_workspace_files(
            workspace_id=workspace.workspace_id,
        )
        
        # Should have all files
        assert len(statuses) == 4
        
        # All should be linked initially
        for status in statuses.values():
            assert status == FileStatus.LINKED
    
    def test_scan_with_modifications(self, cow_setup):
        """Test scanning workspace with modifications."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify one file
        (original_dir / "src" / "main.py").write_text("modified")
        
        statuses = cow_engine.scan_workspace_files(
            workspace_id=workspace.workspace_id,
            detect_modifications=True,
        )
        
        # Check modification detected
        assert statuses["src/main.py"] == FileStatus.COPIED
    
    def test_sync_modifications(self, cow_setup):
        """Test syncing all modifications."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Modify multiple files
        (original_dir / "src" / "main.py").write_text("modified main")
        (original_dir / "config.yaml").write_text("modified config")
        
        copied_files = cow_engine.sync_modifications(
            workspace_id=workspace.workspace_id,
        )
        
        assert len(copied_files) == 2
        assert "src/main.py" in copied_files
        assert "config.yaml" in copied_files


class TestCOWEngineEdgeCases:
    """Tests for edge cases in COW engine."""
    
    def test_nonexistent_file(self, cow_setup):
        """Test handling nonexistent file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        
        status = cow_engine.get_file_status(
            workspace_id=workspace.workspace_id,
            rel_path="nonexistent.py",
        )
        
        assert status == FileStatus.UNKNOWN
    
    def test_empty_file(self, cow_setup):
        """Test handling empty file."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Create empty file
        empty_file = original_dir / "empty.txt"
        empty_file.write_text("")
        
        state = cow_engine.create_linked_file(
            workspace_id=workspace.workspace_id,
            rel_path="empty.txt",
            original_path=empty_file,
        )
        
        assert state.status == FileStatus.LINKED
        assert state.original_size == 0
    
    def test_symlink_chain(self, cow_setup):
        """Test handling symlink chain."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Initialize links
        cow_engine.initialize_workspace_links(
            workspace_id=workspace.workspace_id,
            original_path=workspace.original_path,
        )
        
        # Verify symlink chain
        workspace_file = Path(workspace.workspace_dir) / "src" / "main.py"
        
        # Symlink points to original
        assert workspace_file.is_symlink()
        target = workspace_file.resolve()
        assert target == (original_dir / "src" / "main.py").resolve()
        
        # Modify and copy-up
        (original_dir / "src" / "main.py").write_text("modified")
        cow_engine.copy_up(
            workspace_id=workspace.workspace_id,
            rel_path="src/main.py",
        )
        
        # Now symlink should point to COW copy
        assert workspace_file.is_symlink()
        new_target = workspace_file.resolve()
        copies_dir = Path(workspace.copies_dir).resolve()
        assert copies_dir in new_target.parents or new_target.parent.resolve() == copies_dir
    
    def test_nested_directory(self, cow_setup):
        """Test handling nested directories."""
        cow_engine = cow_setup["cow_engine"]
        workspace = cow_setup["workspace"]
        original_dir = cow_setup["original_dir"]
        
        # Create nested file
        nested_dir = original_dir / "deep" / "nested" / "path"
        nested_dir.mkdir(parents=True)
        nested_file = nested_dir / "file.py"
        nested_file.write_text("nested content")
        
        state = cow_engine.create_linked_file(
            workspace_id=workspace.workspace_id,
            rel_path="deep/nested/path/file.py",
            original_path=nested_file,
        )
        
        assert state.status == FileStatus.LINKED
        
        # Verify nested directory created in workspace
        workspace_file = Path(workspace.workspace_dir) / "deep" / "nested" / "path" / "file.py"
        assert workspace_file.exists()
        assert workspace_file.is_symlink()