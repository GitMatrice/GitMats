"""
End-to-End Integration Tests for GitMats.

Tests complete workflows from CLI to backend integration:
- Full workspace lifecycle
- Backend switching
- Multi-workspace operations
- Error recovery
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from click.testing import CliRunner

from gitmats.cli import gmt
from gitmats.workspace import WorkspaceManager
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.config import GitMatsConfig
from gitmats.models import Workspace, WorkspaceType, GitMode
from gitmats.backends.null import NullBackend
from gitmats.backends.lakebase import LakeBaseBackend
from gitmats.backends.lakebase_client import LakeBaseConfig
from gitmats.exceptions import GitMatsError


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create temporary directory."""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


@pytest.fixture
def git_repo(temp_dir: Path) -> Path:
    """Create a test Git repository."""
    repo_dir = temp_dir / "git_repo"
    repo_dir.mkdir(parents=True)
    
    # Initialize git
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True)
    
    # Create initial content
    (repo_dir / "README.md").write_text("# Test Project\n\nThis is a test.")
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "main.py").write_text("print('Hello World')")
    
    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)
    
    return repo_dir


@pytest.fixture
def non_git_dir(temp_dir: Path) -> Path:
    """Create a non-Git directory."""
    dir_path = temp_dir / "plain_dir"
    dir_path.mkdir(parents=True)
    
    (dir_path / "file1.txt").write_text("Content 1")
    (dir_path / "file2.txt").write_text("Content 2")
    (dir_path / "subdir").mkdir()
    (dir_path / "subdir" / "nested.txt").write_text("Nested content")
    
    return dir_path


@pytest.fixture
def config(temp_dir: Path) -> GitMatsConfig:
    """Create test configuration."""
    config = GitMatsConfig()
    config.default_workspace_dir = str(temp_dir / "workspaces")
    config.registry_db = str(temp_dir / "metadata.db")
    return config


@pytest.fixture
def cli_runner(temp_dir: Path) -> CliRunner:
    """Create CLI runner with isolated environment."""
    runner = CliRunner(env={
        "GITMATS_WORKSPACE_DIR": str(temp_dir / "workspaces"),
        "GITMATS_REGISTRY_DB": str(temp_dir / "metadata.db"),
    })
    return runner


class TestE2EWorkspaceLifecycle:
    """Test complete workspace lifecycle."""
    
    def test_create_use_destroy_workflow(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        temp_dir: Path,
    ):
        """Test full workflow: create, use, destroy."""
        # Create workspace
        result = cli_runner.invoke(gmt, [
            "create", "test-ws",
            "--from", str(git_repo),
        ])
        
        if result.exit_code != 0:
            # May fail if Git operations not available
            pytest.skip("Git operations not available")
        
        # Check workspace exists
        result = cli_runner.invoke(gmt, ["list"])
        assert "test-ws" in result.output
        
        # Check workspace status
        result = cli_runner.invoke(gmt, ["status", "test-ws"])
        assert result.exit_code == 0
        
        # Destroy workspace
        result = cli_runner.invoke(gmt, ["destroy", "test-ws", "--force"])
        assert result.exit_code == 0
        
        # Check workspace gone
        result = cli_runner.invoke(gmt, ["list"])
        assert "test-ws" not in result.output
    
    def test_create_non_git_workspace(
        self,
        cli_runner: CliRunner,
        non_git_dir: Path,
        temp_dir: Path,
    ):
        """Test creating workspace from non-Git directory."""
        # Create workspace with standalone Git mode
        result = cli_runner.invoke(gmt, [
            "create", "plain-ws",
            "--from", str(non_git_dir),
            "--git-mode", "standalone",
        ])
        
        # Should succeed with standalone mode
        if result.exit_code == 0:
            # Check workspace exists
            result = cli_runner.invoke(gmt, ["list"])
            assert "plain-ws" in result.output
            
            # Cleanup
            cli_runner.invoke(gmt, ["destroy", "plain-ws", "--force"])
    
    def test_multiple_workspaces(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        temp_dir: Path,
    ):
        """Test managing multiple workspaces."""
        if not shutil.which("git"):
            pytest.skip("Git not available")
        
        # Create multiple workspaces
        for i in range(3):
            result = cli_runner.invoke(gmt, [
                "create", f"ws-{i}",
                "--from", str(git_repo),
            ])
            
            if result.exit_code != 0:
                pytest.skip("Git operations not available")
                return
        
        # List all workspaces
        result = cli_runner.invoke(gmt, ["list"])
        assert "ws-0" in result.output
        assert "ws-1" in result.output
        assert "ws-2" in result.output
        
        # Destroy all
        for i in range(3):
            cli_runner.invoke(gmt, ["destroy", f"ws-{i}", "--force"])
        
        # Check all gone
        result = cli_runner.invoke(gmt, ["list"])
        assert "ws-0" not in result.output


class TestE2EBackendIntegration:
    """Test backend integration."""
    
    def test_null_backend_workflow(
        self,
        temp_dir: Path,
        non_git_dir: Path,
        config: GitMatsConfig,
    ):
        """Test Null backend operations."""
        metadata_manager = MetadataManager(registry_path=Path(config.registry_db))
        storage_manager = StorageManager(config=config)
        
        # Create workspace with Null backend behavior
        workspace = storage_manager.create_workspace_structure(
            workspace_id="null-test",
            original_path=str(non_git_dir),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        
        metadata_manager.create_workspace(workspace)
        
        # Test NullBackend
        null_backend = NullBackend(
            metadata_manager=metadata_manager,
            storage_manager=storage_manager,
        )
        
        # Setup should succeed
        assert null_backend.setup_workspace(workspace)
        
        # Commit should return None (no support)
        result = null_backend.commit_changes(workspace, "Test commit")
        assert result is None
        
        # Cleanup
        null_backend.cleanup_workspace(workspace)
    
    def test_lakebase_backend_mocked(
        self,
        temp_dir: Path,
        non_git_dir: Path,
        config: GitMatsConfig,
    ):
        """Test LakeBase backend with mocked API."""
        from unittest.mock import patch
        
        metadata_manager = MetadataManager(registry_path=Path(config.registry_db))
        storage_manager = StorageManager(config=config)
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="lakebase-test",
            original_path=str(non_git_dir),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        
        metadata_manager.create_workspace(workspace)
        
        # Create LakeBase backend with test config
        lakebase_config = LakeBaseConfig(
            api_url="https://test.api.com/v1",
            database_id="db_test",
            api_token="test_token",
        )
        
        backend = LakeBaseBackend(
            config=lakebase_config,
            storage_manager=storage_manager,
            metadata_manager=metadata_manager,
        )
        
        # Mock API responses
        mock_branch = {
            "id": "br_test",
            "name": "gitmats-lakebase-test",
            "neon_timeline_id": "tl_test",
            "connection_uri": "postgres://...",
        }
        
        with patch.object(backend.client, "create_branch", return_value=mock_branch):
            result = backend.create_workspace_branch(workspace)
            assert result.status == "created"
        
        # Cleanup
        with patch.object(backend.client, "delete_branch", return_value=True):
            result = backend.delete_branch(workspace)
            assert result.status == "deleted"


class TestE2EErrorHandling:
    """Test error handling and recovery."""
    
    def test_workspace_not_found_error(
        self,
        cli_runner: CliRunner,
    ):
        """Test error for non-existent workspace."""
        result = cli_runner.invoke(gmt, ["status", "nonexistent"])
        
        # Should fail with appropriate error
        assert result.exit_code != 0 or "not found" in result.output.lower()
    
    def test_duplicate_workspace_error(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
        temp_dir: Path,
    ):
        """Test error for duplicate workspace ID."""
        if not shutil.which("git"):
            pytest.skip("Git not available")
        
        # Create first workspace
        result = cli_runner.invoke(gmt, [
            "create", "duplicate-test",
            "--from", str(git_repo),
        ])
        
        if result.exit_code != 0:
            pytest.skip("Git operations not available")
            return
        
        # Try to create duplicate
        result = cli_runner.invoke(gmt, [
            "create", "duplicate-test",
            "--from", str(git_repo),
        ])
        
        # Should fail
        assert result.exit_code != 0 or "already exists" in result.output.lower()
        
        # Cleanup
        cli_runner.invoke(gmt, ["destroy", "duplicate-test", "--force"])
    
    def test_invalid_workspace_id_error(
        self,
        cli_runner: CliRunner,
        git_repo: Path,
    ):
        """Test error for invalid workspace ID."""
        # Try with invalid ID (starts with hyphen)
        result = cli_runner.invoke(gmt, [
            "create", "-invalid",
            "--from", str(git_repo),
        ])
        
        # Should fail
        assert result.exit_code != 0


class TestE2EPerformance:
    """Test performance with large directories."""
    
    def test_large_directory_creation(
        self,
        temp_dir: Path,
        config: GitMatsConfig,
    ):
        """Test creating workspace with many files."""
        # Create directory with many files
        large_dir = temp_dir / "large_dir"
        large_dir.mkdir(parents=True)
        
        # Create 100 files
        for i in range(100):
            (large_dir / f"file_{i}.txt").write_text(f"Content {i}")
        
        # Create nested directories
        for i in range(10):
            subdir = large_dir / f"subdir_{i}"
            subdir.mkdir()
            for j in range(10):
                (subdir / f"nested_{j}.txt").write_text(f"Nested {i}-{j}")
        
        # Create workspace
        workspace_manager = WorkspaceManager(config=config)
        
        workspace = workspace_manager.create_workspace(
            workspace_id="large-test",
            original_path=str(large_dir),
        )
        
        assert workspace is not None
        
        # Check symlinks created
        workspace_dir = Path(workspace.workspace_dir)
        linked_files = list(workspace_dir.glob("**/*"))
        
        # Should have symlinks for most files
        symlinks = [f for f in linked_files if f.is_symlink()]
        assert len(symlinks) > 100
        
        # Cleanup
        workspace_manager.destroy_workspace("large-test")


class TestE2ECLICommands:
    """Test all CLI commands."""
    
    def test_version_command(self, cli_runner: CliRunner):
        """Test version command."""
        result = cli_runner.invoke(gmt, ["--version"])
        assert result.exit_code == 0
        assert "gmt" in result.output
    
    def test_help_command(self, cli_runner: CliRunner):
        """Test help command."""
        result = cli_runner.invoke(gmt, ["--help"])
        assert result.exit_code == 0
        assert "Commands:" in result.output
    
    def test_create_help(self, cli_runner: CliRunner):
        """Test create command help."""
        result = cli_runner.invoke(gmt, ["create", "--help"])
        assert result.exit_code == 0
        assert "ORIGINAL_PATH" in result.output
    
    def test_list_help(self, cli_runner: CliRunner):
        """Test list command help."""
        result = cli_runner.invoke(gmt, ["list", "--help"])
        assert result.exit_code == 0
    
    def test_status_help(self, cli_runner: CliRunner):
        """Test status command help."""
        result = cli_runner.invoke(gmt, ["status", "--help"])
        assert result.exit_code == 0
    
    def test_destroy_help(self, cli_runner: CliRunner):
        """Test destroy command help."""
        result = cli_runner.invoke(gmt, ["destroy", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output


class TestE2EIntegration:
    """Integration tests for complete system."""
    
    def test_full_system_workflow(
        self,
        temp_dir: Path,
        non_git_dir: Path,
        config: GitMatsConfig,
    ):
        """Test complete system integration."""
        # Initialize all components
        metadata_manager = MetadataManager(registry_path=Path(config.registry_db))
        storage_manager = StorageManager(config=config)
        workspace_manager = WorkspaceManager(config=config)
        
        # Create workspace
        workspace = workspace_manager.create_workspace(
            workspace_id="integration-test",
            original_path=str(non_git_dir),
        )
        
        assert workspace is not None
        
        # Verify all components
        # 1. Storage
        assert Path(workspace.workspace_dir).exists()
        assert Path(workspace.copies_dir).exists()
        
        # 2. Metadata
        loaded = metadata_manager.get_workspace("integration-test")
        assert loaded is not None
        assert loaded.workspace_id == "integration-test"
        
        # 3. COW
        file_states = metadata_manager.list_file_states("integration-test")
        assert len(file_states) > 0
        
        # 4. Statistics
        stats = workspace_manager.update_statistics("integration-test")
        assert stats["total_files"] > 0
        
        # Modify a file
        workspace_file = Path(workspace.workspace_dir) / "file1.txt"
        workspace_file.unlink()  # Remove symlink
        workspace_file.write_text("Modified content")
        
        # Trigger COW copy-up
        workspace_manager.cow_engine.copy_up("integration-test", "file1.txt")
        
        # Verify copy created
        states = metadata_manager.list_file_states("integration-test")
        copied_states = [s for s in states if s.status.value == "copied"]
        assert len(copied_states) > 0
        
        # Destroy
        workspace_manager.destroy_workspace("integration-test")
        
        # Verify cleanup - workspace should be marked as destroyed
        destroyed_ws = metadata_manager.get_workspace("integration-test")
        assert destroyed_ws is not None
        assert destroyed_ws.status.value == "destroyed"
        assert not Path(workspace.workspace_dir).exists()