"""Tests for GitMats data models."""

from datetime import datetime

import pytest

from gitmats.models import (
    Workspace,
    FileState,
    WorkspaceConfig,
    GitCommit,
    OperationLog,
    WorkspaceType,
    WorkspaceStatus,
    GitMode,
    FileStatus,
    CommitType,
    OperationType,
)


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = WorkspaceConfig()
        assert config.auto_commit is False
        assert config.commit_prefix == ""
        assert config.sync_on_destroy is False
        assert config.lock_after_create is False
        assert config.hooks_enabled is True
        assert config.max_disk_usage_mb == 0
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = WorkspaceConfig(
            auto_commit=True,
            commit_prefix="[WIP]",
            max_disk_usage_mb=100,
        )
        assert config.auto_commit is True
        assert config.commit_prefix == "[WIP]"
        assert config.max_disk_usage_mb == 100


class TestWorkspace:
    """Tests for Workspace dataclass."""
    
    def test_workspace_creation(self):
        """Test creating a workspace."""
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/path/to/original",
            storage_path="/path/to/storage",
            workspace_dir="/path/to/workspace",
            git_dir="/path/to/git",
            copies_dir="/path/to/copies",
            metadata_db="/path/to/metadata.db",
            workspace_type=WorkspaceType.INHERITED,
            status=WorkspaceStatus.ACTIVE,
            created_at=datetime.now(),
            last_accessed=None,
            created_by="user",
            git_mode=GitMode.INHERITED,
            git_branch="main",
            git_head=None,
        )
        
        assert workspace.workspace_id == "test-123"
        assert workspace.workspace_type == WorkspaceType.INHERITED
        assert workspace.status == WorkspaceStatus.ACTIVE
        assert workspace.git_mode == GitMode.INHERITED
    
    def test_workspace_to_dict(self):
        """Test workspace serialization."""
        created_at = datetime(2025, 6, 6, 10, 30, 0)
        workspace = Workspace(
            workspace_id="test-123",
            original_path="/original",
            storage_path="/storage",
            workspace_dir="/workspace",
            git_dir="/git",
            copies_dir="/copies",
            metadata_db="/metadata.db",
            workspace_type=WorkspaceType.STANDALONE,
            status=WorkspaceStatus.ACTIVE,
            created_at=created_at,
            last_accessed=None,
            created_by=None,
            git_mode=GitMode.STANDALONE,
            git_branch=None,
            git_head=None,
        )
        
        data = workspace.to_dict()
        
        assert data["workspace_id"] == "test-123"
        assert data["workspace_type"] == "standalone"
        assert data["status"] == "active"
        assert data["created_at"] == created_at.isoformat()
    
    def test_workspace_from_dict(self):
        """Test workspace deserialization."""
        data = {
            "workspace_id": "test-123",
            "original_path": "/original",
            "storage_path": "/storage",
            "workspace_dir": "/workspace",
            "git_dir": "/git",
            "copies_dir": "/copies",
            "metadata_db": "/metadata.db",
            "workspace_type": "inherited",
            "status": "active",
            "created_at": "2025-06-06T10:30:00",
            "last_accessed": None,
            "created_by": None,
            "git_mode": "inherited",
            "git_branch": "main",
            "git_head": "abc123",
            "total_files": 10,
            "config": {},
            "backend_meta": {},
        }
        
        workspace = Workspace.from_dict(data)
        
        assert workspace.workspace_id == "test-123"
        assert workspace.workspace_type == WorkspaceType.INHERITED
        assert workspace.git_branch == "main"


class TestFileState:
    """Tests for FileState dataclass."""
    
    def test_linked_file(self):
        """Test file in linked state."""
        state = FileState(
            workspace_id="test-123",
            relative_path="src/main.py",
            status=FileStatus.LINKED,
            original_hash="abc123",
            original_size=100,
        )
        
        assert state.status == FileStatus.LINKED
        assert state.relative_path == "src/main.py"
        assert state.modification_count == 0
    
    def test_copied_file(self):
        """Test file in copied state."""
        state = FileState(
            workspace_id="test-123",
            relative_path="src/main.py",
            status=FileStatus.COPIED,
            original_hash="abc123",
            original_size=100,
            cow_path="/copies/src/main.py",
            cow_hash="def456",
            cow_size=150,
            modification_count=1,
        )
        
        assert state.status == FileStatus.COPIED
        assert state.cow_path == "/copies/src/main.py"
    
    def test_file_state_serialization(self):
        """Test file state to_dict/from_dict."""
        state = FileState(
            workspace_id="test-123",
            relative_path="test.py",
            status=FileStatus.NEW,
            cow_path="/copies/test.py",
            cow_hash="xyz789",
            cow_size=50,
        )
        
        data = state.to_dict()
        restored = FileState.from_dict(data)
        
        assert restored.workspace_id == state.workspace_id
        assert restored.status == state.status
        assert restored.cow_path == state.cow_path


class TestGitCommit:
    """Tests for GitCommit dataclass."""
    
    def test_commit_creation(self):
        """Test creating a commit."""
        commit = GitCommit(
            workspace_id="test-123",
            commit_sha="abc123def456",
            commit_message="Add feature",
            author_name="Test User",
            author_email="test@test.com",
            authored_at=datetime.now(),
            commit_type=CommitType.USER,
            files_changed=3,
        )
        
        assert commit.commit_sha == "abc123def456"
        assert commit.commit_type == CommitType.USER
    
    def test_commit_serialization(self):
        """Test commit serialization."""
        commit = GitCommit(
            workspace_id="test",
            commit_sha="abc123",
            commit_message="Test",
            commit_type=CommitType.BASE,
        )
        
        data = commit.to_dict()
        restored = GitCommit.from_dict(data)
        
        assert restored.commit_sha == commit.commit_sha
        assert restored.commit_type == CommitType.BASE


class TestOperationLog:
    """Tests for OperationLog dataclass."""
    
    def test_operation_log_creation(self):
        """Test creating an operation log."""
        log = OperationLog(
            workspace_id="test-123",
            operation_type=OperationType.COPY_UP,
            relative_path="src/main.py",
            timestamp=datetime.now(),
            success=True,
        )
        
        assert log.operation_type == OperationType.COPY_UP
        assert log.success is True
    
    def test_failed_operation(self):
        """Test failed operation log."""
        log = OperationLog(
            workspace_id="test-123",
            operation_type=OperationType.GIT_COMMIT,
            timestamp=datetime.now(),
            success=False,
            error_message="Failed to commit",
        )
        
        assert log.success is False
        assert log.error_message == "Failed to commit"


class TestEnums:
    """Tests for enum values."""
    
    def test_workspace_type_values(self):
        """Test workspace type enum values."""
        assert WorkspaceType.INHERITED.value == "inherited"
        assert WorkspaceType.STANDALONE.value == "standalone"
    
    def test_file_status_values(self):
        """Test file status enum values."""
        assert FileStatus.LINKED.value == "linked"
        assert FileStatus.COPIED.value == "copied"
        assert FileStatus.NEW.value == "new"
        assert FileStatus.DELETED.value == "deleted"
    
    def test_status_transitions(self):
        """Test workspace status values."""
        assert WorkspaceStatus.ACTIVE.value == "active"
        assert WorkspaceStatus.LOCKED.value == "locked"
        assert WorkspaceStatus.DESTROYED.value == "destroyed"