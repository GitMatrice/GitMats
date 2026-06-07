"""
Tests for LakeBase Backend.

Tests LakeBase versioning backend using mocked API responses.
"""

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch, MagicMock

import pytest

from gitmats.models import Workspace, WorkspaceType, GitMode, WorkspaceStatus
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.backends.lakebase import LakeBaseBackend
from gitmats.backends.lakebase_client import LakeBaseConfig, LakeBaseError
from gitmats.backends.interface import (
    BranchResult,
    CommitResult,
    VersionInfo,
    DiffResult,
    RestoreResult,
    DeleteResult,
    FileChange,
)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def lakebase_config() -> LakeBaseConfig:
    """Create LakeBase configuration."""
    return LakeBaseConfig(
        api_url="https://api.example.com/api/v1",
        database_id="db_test123",
        api_token="test_token_xxx",
        branch_prefix="gitmats-",
        parent_branch="main",
    )


@pytest.fixture
def metadata_manager(temp_dir: Path) -> MetadataManager:
    """Create metadata manager."""
    db_path = temp_dir / "metadata.db"
    return MetadataManager(registry_path=db_path)


@pytest.fixture
def storage_manager(temp_dir: Path, metadata_manager: MetadataManager) -> StorageManager:
    """Create storage manager."""
    workspace_dir = temp_dir / "workspaces"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    from gitmats.config import GitMatsConfig
    config = GitMatsConfig()
    config.default_workspace_dir = str(workspace_dir)
    config.registry_db = str(temp_dir / "metadata.db")
    
    return StorageManager(config=config)


@pytest.fixture
def lakebase_backend(
    lakebase_config: LakeBaseConfig,
    storage_manager: StorageManager,
    metadata_manager: MetadataManager,
) -> LakeBaseBackend:
    """Create LakeBase backend."""
    return LakeBaseBackend(
        config=lakebase_config,
        storage_manager=storage_manager,
        metadata_manager=metadata_manager,
    )


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
        workspace_id="test-lakebase",
        original_path=str(original_path),
        workspace_type=WorkspaceType.STANDALONE,
        git_mode=GitMode.STANDALONE,
    )
    metadata_manager.create_workspace(workspace)
    
    return workspace


class TestLakeBaseConfig:
    """Tests for LakeBase configuration."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = LakeBaseConfig()
        
        assert config.api_url == "https://api.dbay.cloud:8443/api/v1"
        assert config.branch_prefix == "gitmats-"
        assert config.parent_branch == "main"
    
    def test_config_from_env(self):
        """Test configuration from environment."""
        import os
        
        # Set environment variables
        os.environ["LAKEBASE_API_URL"] = "https://custom.api.com/v1"
        os.environ["LAKEBASE_DATABASE_ID"] = "db_custom"
        os.environ["LAKEBASE_API_TOKEN"] = "custom_token"
        
        config = LakeBaseConfig.from_env()
        
        assert config.api_url == "https://custom.api.com/v1"
        assert config.database_id == "db_custom"
        assert config.api_token == "custom_token"
        
        # Clean up
        del os.environ["LAKEBASE_API_URL"]
        del os.environ["LAKEBASE_DATABASE_ID"]
        del os.environ["LAKEBASE_API_TOKEN"]
    
    def test_config_validation_valid(self, lakebase_config: LakeBaseConfig):
        """Test validation with valid config."""
        errors = lakebase_config.validate()
        assert len(errors) == 0
    
    def test_config_validation_missing_database(self):
        """Test validation with missing database_id."""
        config = LakeBaseConfig(api_token="test")
        errors = config.validate()
        
        assert "database_id is required" in errors
    
    def test_config_validation_missing_token(self):
        """Test validation with missing api_token."""
        config = LakeBaseConfig(database_id="db_test")
        errors = config.validate()
        
        assert any("api_token is required" in e for e in errors)


class TestLakeBaseBranch:
    """Tests for LakeBase branch operations."""
    
    def test_create_branch_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful branch creation."""
        # Mock client response
        mock_response = {
            "id": "br_xyz123",
            "name": "gitmats-test-lakebase",
            "neon_timeline_id": "tl_abc456",
            "connection_uri": "postgres://user@host/db",
        }
        
        with patch.object(
            lakebase_backend.client,
            "create_branch",
            return_value=mock_response,
        ):
            result = lakebase_backend.create_workspace_branch(sample_workspace)
        
        assert result.status == "created"
        assert result.branch_id == "br_xyz123"
        assert result.connection_uri == "postgres://user@host/db"
        
        # Check workspace metadata updated
        assert sample_workspace.backend_meta.get("lakebase_branch_id") == "br_xyz123"
    
    def test_create_branch_api_error(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test branch creation with API error."""
        with patch.object(
            lakebase_backend.client,
            "create_branch",
            side_effect=LakeBaseError("API unavailable", status_code=503),
        ):
            result = lakebase_backend.create_workspace_branch(sample_workspace)
        
        assert result.status == "error"
        assert "API unavailable" in result.message
    
    def test_create_branch_missing_config(
        self,
        storage_manager: StorageManager,
        metadata_manager: MetadataManager,
        sample_workspace: Workspace,
    ):
        """Test branch creation with invalid config."""
        invalid_config = LakeBaseConfig()  # Missing database_id and api_token
        
        backend = LakeBaseBackend(
            config=invalid_config,
            storage_manager=storage_manager,
            metadata_manager=metadata_manager,
        )
        
        result = backend.create_workspace_branch(sample_workspace)
        
        assert result.status == "error"
        assert "Configuration errors" in result.message
    
    def test_delete_branch_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful branch deletion."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        with patch.object(
            lakebase_backend.client,
            "delete_branch",
            return_value=True,
        ):
            result = lakebase_backend.delete_branch(sample_workspace)
        
        assert result.status == "deleted"
    
    def test_delete_branch_protected(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test deletion of protected branch."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_main",
        }
        
        with patch.object(
            lakebase_backend.client,
            "delete_branch",
            return_value=False,  # Default branch cannot be deleted
        ):
            result = lakebase_backend.delete_branch(sample_workspace)
        
        assert result.status == "protected"
    
    def test_delete_branch_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test deletion with no branch."""
        sample_workspace.backend_meta = {}
        
        result = lakebase_backend.delete_branch(sample_workspace)
        
        assert result.status == "no_branch"


class TestLakeBaseCommit:
    """Tests for LakeBase commit/version operations."""
    
    def test_commit_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful version creation."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        mock_response = {
            "id": "ver_abc123",
            "created_at": "2024-01-15T10:30:00Z",
            "lsn": "0/12345",
        }
        
        files = [
            FileChange(path="file1.txt", change_type="modify"),
            FileChange(path="file2.txt", change_type="add"),
        ]
        
        with patch.object(
            lakebase_backend.client,
            "create_version",
            return_value=mock_response,
        ):
            result = lakebase_backend.commit(
                workspace=sample_workspace,
                message="Test commit",
                files=files,
            )
        
        assert result.status == "committed"
        assert result.version_id == "ver_abc123"
        assert result.lsn == "0/12345"
    
    def test_commit_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test commit without branch."""
        sample_workspace.backend_meta = {}
        
        result = lakebase_backend.commit(
            workspace=sample_workspace,
            message="Test commit",
        )
        
        assert result.status == "error"
        assert "no LakeBase branch" in result.message
    
    def test_commit_api_error(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test commit with API error."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        with patch.object(
            lakebase_backend.client,
            "create_version",
            side_effect=LakeBaseError("Internal error", status_code=500),
        ):
            result = lakebase_backend.commit(
                workspace=sample_workspace,
                message="Test commit",
            )
        
        assert result.status == "error"


class TestLakeBaseVersions:
    """Tests for LakeBase version listing and retrieval."""
    
    def test_list_versions_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful version listing."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        mock_response = {
            "versions": [
                {
                    "id": "ver_1",
                    "name": "Initial commit",
                    "created_at": "2024-01-10T10:00:00Z",
                    "lsn": "0/1000",
                },
                {
                    "id": "ver_2",
                    "name": "Add feature",
                    "created_at": "2024-01-15T10:00:00Z",
                    "lsn": "0/2000",
                },
            ],
        }
        
        with patch.object(
            lakebase_backend.client,
            "list_versions",
            return_value=mock_response.get("versions", []),
        ):
            versions = lakebase_backend.list_versions(sample_workspace)
        
        assert len(versions) == 2
        assert versions[0].version_id == "ver_1"
        assert versions[0].name == "Initial commit"
    
    def test_list_versions_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test listing versions without branch."""
        sample_workspace.backend_meta = {}
        
        versions = lakebase_backend.list_versions(sample_workspace)
        
        assert len(versions) == 0
    
    def test_get_version_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test getting specific version."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        mock_response = {
            "id": "ver_1",
            "name": "Initial commit",
            "description": "First version",
            "created_at": "2024-01-10T10:00:00Z",
            "lsn": "0/1000",
        }
        
        with patch.object(
            lakebase_backend.client,
            "get_version",
            return_value=mock_response,
        ):
            version = lakebase_backend.get_version(sample_workspace, "ver_1")
        
        assert version is not None
        assert version.version_id == "ver_1"
        assert version.description == "First version"
    
    def test_get_version_not_found(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test getting non-existent version."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        with patch.object(
            lakebase_backend.client,
            "get_version",
            side_effect=LakeBaseError("Not found", status_code=404),
        ):
            version = lakebase_backend.get_version(sample_workspace, "ver_nonexistent")
        
        assert version is None


class TestLakeBaseDiff:
    """Tests for LakeBase diff operations."""
    
    def test_diff_versions_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful version diff."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        mock_schema_diff = {
            "changes": [
                {"type": "created", "object": "table_new"},
            ],
        }
        
        mock_data_diff = {
            "changes": [
                {"table": "gitmats_file_metadata", "key": "file1.txt", "type": "modified"},
                {"table": "gitmats_file_metadata", "key": "file2.txt", "type": "added"},
            ],
        }
        
        with patch.object(
            lakebase_backend.client,
            "diff_schema",
            return_value=mock_schema_diff,
        ), patch.object(
            lakebase_backend.client,
            "diff_data",
            return_value=mock_data_diff,
        ):
            result = lakebase_backend.diff_versions(
                workspace=sample_workspace,
                source_id="ver_1",
                target_id="ver_2",
            )
        
        assert result.source_id == "ver_1"
        assert result.target_id == "ver_2"
        assert "file1.txt" in result.files_changed
        assert "1 schema changes" in result.summary
    
    def test_diff_versions_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test diff without branch."""
        sample_workspace.backend_meta = {}
        
        result = lakebase_backend.diff_versions(
            workspace=sample_workspace,
            source_id="ver_1",
            target_id="ver_2",
        )
        
        assert "No LakeBase branch" in result.summary


class TestLakeBaseRestore:
    """Tests for LakeBase restore operations."""
    
    def test_restore_version_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test successful version restore."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
            "lakebase_timeline_id": "tl_old",
        }
        
        mock_response = {
            "new_timeline_id": "tl_new",
            "backup_branch_id": "br_backup",
        }
        
        with patch.object(
            lakebase_backend.client,
            "restore_version",
            return_value=mock_response,
        ), patch.object(
            lakebase_backend.metadata_manager,
            "update_workspace",
        ):
            result = lakebase_backend.restore_version(
                workspace=sample_workspace,
                version_id="ver_1",
            )
        
        assert result.status == "restored"
        assert result.new_timeline_id == "tl_new"
    
    def test_restore_version_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test restore without branch."""
        sample_workspace.backend_meta = {}
        
        result = lakebase_backend.restore_version(
            workspace=sample_workspace,
            version_id="ver_1",
        )
        
        assert result.status == "error"
        assert "No LakeBase branch" in result.message


class TestLakeBaseStatus:
    """Tests for LakeBase status operations."""
    
    def test_get_status_success(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test getting workspace status."""
        sample_workspace.backend_meta = {
            "lakebase_branch_id": "br_xyz123",
        }
        
        mock_branch = {
            "id": "br_xyz123",
            "name": "gitmats-test",
            "neon_timeline_id": "tl_abc",
            "connection_uri": "postgres://...",
        }
        
        mock_compute = {
            "status": "running",
        }
        
        with patch.object(
            lakebase_backend.client,
            "get_branch",
            return_value=mock_branch,
        ), patch.object(
            lakebase_backend.client,
            "get_compute_status",
            return_value=mock_compute,
        ):
            status = lakebase_backend.get_status(sample_workspace)
        
        assert status["backend"] == "lakebase"
        assert status["branch_name"] == "gitmats-test"
        assert status["compute_status"] == "running"
    
    def test_get_status_no_branch(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test status without branch."""
        sample_workspace.backend_meta = {}
        
        status = lakebase_backend.get_status(sample_workspace)
        
        assert status["backend"] == "lakebase"
        assert status["status"] == "no_branch"


class TestLakeBaseIntegration:
    """Integration tests for LakeBase backend."""
    
    def test_full_workflow_mocked(
        self,
        lakebase_backend: LakeBaseBackend,
        sample_workspace: Workspace,
    ):
        """Test complete workflow with mocked API."""
        # Mock all API calls
        mock_branch = {
            "id": "br_workflow",
            "name": "gitmats-workflow",
            "neon_timeline_id": "tl_workflow",
            "connection_uri": "postgres://...",
        }
        
        mock_version_1 = {
            "id": "ver_initial",
            "created_at": "2024-01-10T10:00:00Z",
            "lsn": "0/1000",
        }
        
        mock_version_2 = {
            "id": "ver_final",
            "created_at": "2024-01-15T10:00:00Z",
            "lsn": "0/2000",
        }
        
        mock_versions = [
            {"id": "ver_initial", "name": "Initial", "created_at": "2024-01-10T10:00:00Z"},
            {"id": "ver_final", "name": "Final", "created_at": "2024-01-15T10:00:00Z"},
        ]
        
        mock_restore = {
            "new_timeline_id": "tl_restored",
        }
        
        with patch.object(
            lakebase_backend.client, "create_branch", return_value=mock_branch
        ), patch.object(
            lakebase_backend.client, "create_version", return_value=mock_version_1
        ), patch.object(
            lakebase_backend.client, "list_versions", return_value=mock_versions
        ), patch.object(
            lakebase_backend.client, "restore_version", return_value=mock_restore
        ), patch.object(
            lakebase_backend.client, "delete_branch", return_value=True
        ), patch.object(
            lakebase_backend.metadata_manager, "update_workspace"
        ):
            # Create branch
            branch_result = lakebase_backend.create_workspace_branch(sample_workspace)
            assert branch_result.status == "created"
            
            # Create commit
            commit_result = lakebase_backend.commit(sample_workspace, "Initial commit")
            assert commit_result.status == "committed"
            
            # List versions
            versions = lakebase_backend.list_versions(sample_workspace)
            assert len(versions) == 2
            
            # Restore
            restore_result = lakebase_backend.restore_version(sample_workspace, "ver_initial")
            assert restore_result.status == "restored"
            
            # Delete
            delete_result = lakebase_backend.delete_branch(sample_workspace)
            assert delete_result.status == "deleted"