"""Tests for GitMats metadata management."""

from datetime import datetime
from pathlib import Path
import tempfile

import pytest

from gitmats.config import GitMatsConfig
from gitmats.metadata import MetadataManager
from gitmats.models import (
    Workspace,
    WorkspaceType,
    WorkspaceStatus,
    GitMode,
    WorkspaceConfig,
    FileState,
    FileStatus,
    GitCommit,
    CommitType,
    OperationLog,
    OperationType,
)


class TestMetadataManager:
    """Tests for MetadataManager."""
    
    def test_init_creates_registry(self, temp_gitmats_root):
        """Test that initialization creates registry database."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        assert registry_path.exists()
    
    def test_create_workspace(self, temp_gitmats_root):
        """Test creating workspace in registry."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-123" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by="user",
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        
        # Verify workspace exists
        retrieved = manager.get_workspace("test-123")
        assert retrieved is not None
        assert retrieved.workspace_id == "test-123"
    
    def test_get_nonexistent_workspace(self, temp_gitmats_root):
        """Test getting workspace that doesn't exist."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = manager.get_workspace("nonexistent")
        assert workspace is None
    
    def test_list_workspaces(self, temp_gitmats_root):
        """Test listing workspaces."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        # Create multiple workspaces
        for i in range(3):
            workspace = Workspace(
                workspace_id=f"test-{i}",
                original_path="/original",
                storage_path="/storage",
                workspace_dir="/workspace",
                git_dir="/git",
                copies_dir="/copies",
                metadata_db=str(temp_gitmats_root / f"test-{i}" / "metadata.db"),
                workspace_type=WorkspaceType.STANDALONE,
                status=WorkspaceStatus.ACTIVE,
                created_at=datetime.now(),
                last_accessed=None,
                created_by=None,
                git_mode=GitMode.STANDALONE,
                git_branch=None,
                git_head=None,
            )
            manager.create_workspace(workspace)
        
        workspaces = manager.list_workspaces()
        assert len(workspaces) == 3
    
    def test_list_workspaces_with_filter(self, temp_gitmats_root):
        """Test listing workspaces with status filter."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        # Create workspaces with different statuses
        for status in [WorkspaceStatus.ACTIVE, WorkspaceStatus.LOCKED]:
            workspace = Workspace(
                workspace_id=f"test-{status.value}",
                original_path="/original",
                storage_path="/storage",
                workspace_dir="/workspace",
                git_dir="/git",
                copies_dir="/copies",
                metadata_db=str(temp_gitmats_root / f"test-{status.value}" / "metadata.db"),
                workspace_type=WorkspaceType.STANDALONE,
                status=status,
                created_at=datetime.now(),
                last_accessed=None,
                created_by=None,
                git_mode=GitMode.STANDALONE,
                git_branch=None,
                git_head=None,
            )
            manager.create_workspace(workspace)
        
        active_workspaces = manager.list_workspaces(status=WorkspaceStatus.ACTIVE)
        assert len(active_workspaces) == 1
        assert active_workspaces[0].status == WorkspaceStatus.ACTIVE
    
    def test_update_workspace(self, temp_gitmats_root):
        """Test updating workspace."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-123" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        
        # Update status
        workspace.status = WorkspaceStatus.LOCKED
        manager.update_workspace(workspace)
        
        retrieved = manager.get_workspace("test-123")
        assert retrieved.status == WorkspaceStatus.LOCKED
    
    def test_delete_workspace(self, temp_gitmats_root):
        """Test deleting workspace."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-123" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        manager.delete_workspace("test-123")
        
        retrieved = manager.get_workspace("test-123")
        assert retrieved is None
    
    def test_update_workspace_stats(self, temp_gitmats_root):
        """Test updating workspace statistics."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-123" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        
        manager.update_workspace_stats(
            workspace_id="test-123",
            total_files=100,
            linked_files=90,
            copied_files=10,
            new_files=0,
            deleted_files=0,
            disk_usage_bytes=1000,
            original_size_bytes=10000,
        )


class TestFileStateOperations:
    """Tests for file state operations."""
    
    @pytest.fixture
    def manager_with_workspace(self, temp_gitmats_root):
        """Create manager with a registered workspace."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-files",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-files" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        return manager
    
    def test_record_linked_file(self, manager_with_workspace):
        """Test recording linked file."""
        manager = manager_with_workspace
        
        manager.record_linked_file(
            workspace_id="test-files",
            rel_path="src/main.py",
            original_hash="abc123",
            original_size=100,
        )
        
        state = manager.get_file_state("test-files", "src/main.py")
        assert state is not None
        assert state.status == FileStatus.LINKED
        assert state.original_hash == "abc123"
    
    def test_record_copy_up(self, manager_with_workspace):
        """Test recording copy-up operation."""
        manager = manager_with_workspace
        
        manager.record_copy_up(
            workspace_id="test-files",
            rel_path="src/main.py",
            original_hash="abc123",
            original_size=100,
            cow_path="/copies/src/main.py",
            cow_hash="def456",
            cow_size=150,
        )
        
        state = manager.get_file_state("test-files", "src/main.py")
        assert state is not None
        assert state.status == FileStatus.COPIED
        assert state.cow_path == "/copies/src/main.py"
    
    def test_record_new_file(self, manager_with_workspace):
        """Test recording new file."""
        manager = manager_with_workspace
        
        manager.record_new_file(
            workspace_id="test-files",
            rel_path="src/new.py",
            cow_path="/copies/src/new.py",
            cow_hash="xyz789",
            cow_size=50,
        )
        
        state = manager.get_file_state("test-files", "src/new.py")
        assert state is not None
        assert state.status == FileStatus.NEW
    
    def test_record_deletion(self, manager_with_workspace):
        """Test recording file deletion."""
        manager = manager_with_workspace
        
        # First record as linked
        manager.record_linked_file(
            workspace_id="test-files",
            rel_path="src/old.py",
            original_hash="abc123",
            original_size=100,
        )
        
        # Then mark as deleted
        manager.record_deletion("test-files", "src/old.py")
        
        state = manager.get_file_state("test-files", "src/old.py")
        assert state.status == FileStatus.DELETED
    
    def test_list_file_states(self, manager_with_workspace):
        """Test listing file states."""
        manager = manager_with_workspace
        
        # Create multiple file states
        manager.record_linked_file("test-files", "file1.py", "hash1", 100)
        manager.record_copy_up("test-files", "file2.py", "hash2", 100, "/copies/file2.py", "hash3", 150)
        manager.record_new_file("test-files", "file3.py", "/copies/file3.py", "hash4", 50)
        
        all_states = manager.list_file_states("test-files")
        assert len(all_states) == 3
        
        copied_states = manager.list_file_states("test-files", status=FileStatus.COPIED)
        assert len(copied_states) == 1


class TestGitCommitOperations:
    """Tests for Git commit operations."""
    
    @pytest.fixture
    def manager_with_workspace(self, temp_gitmats_root):
        """Create manager with a registered workspace."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-commits",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-commits" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        return manager
    
    def test_record_commit(self, manager_with_workspace):
        """Test recording a commit."""
        manager = manager_with_workspace
        
        commit = GitCommit(
            workspace_id="test-commits",
            commit_sha="abc123",
            commit_message="Add feature",
            commit_type=CommitType.USER,
            files_changed=3,
        )
        
        manager.record_commit(commit)
        
        commits = manager.list_commits("test-commits")
        assert len(commits) == 1
        assert commits[0].commit_sha == "abc123"
    
    def test_list_commits(self, manager_with_workspace):
        """Test listing commits."""
        manager = manager_with_workspace
        
        # Record multiple commits
        for i in range(3):
            commit = GitCommit(
                workspace_id="test-commits",
                commit_sha=f"commit{i}",
                commit_message=f"Commit {i}",
                commit_type=CommitType.USER,
            )
            manager.record_commit(commit)
        
        commits = manager.list_commits("test-commits")
        assert len(commits) == 3


class TestOperationLog:
    """Tests for operation logging."""
    
    @pytest.fixture
    def manager_with_workspace(self, temp_gitmats_root):
        """Create manager with a registered workspace."""
        registry_path = temp_gitmats_root / "registry.db"
        manager = MetadataManager(registry_path)
        
        workspace = Workspace(
            workspace_id="test-ops",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db=str(temp_gitmats_root / "test-ops" / "metadata.db"),
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        manager.create_workspace(workspace)
        return manager
    
    def test_log_operation(self, manager_with_workspace):
        """Test logging an operation."""
        manager = manager_with_workspace
        
        log = OperationLog(
            workspace_id="test-ops",
            operation_type=OperationType.COPY_UP,
            relative_path="src/main.py",
            timestamp=datetime.now(),
            success=True,
        )
        
        op_id = manager.log_operation(log)
        assert op_id > 0
    
    def test_log_failed_operation(self, manager_with_workspace):
        """Test logging a failed operation."""
        manager = manager_with_workspace
        
        log = OperationLog(
            workspace_id="test-ops",
            operation_type=OperationType.GIT_COMMIT,
            timestamp=datetime.now(),
            success=False,
            error_message="Failed to commit",
        )
        
        op_id = manager.log_operation(log)
        assert op_id > 0