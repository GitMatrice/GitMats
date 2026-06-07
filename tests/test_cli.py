"""
Tests for GitMats CLI.

Tests CLI commands using click testing utilities.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from click.testing import CliRunner

from gitmats.cli import gmt
from gitmats.config import GitMatsConfig
from gitmats.workspace import WorkspaceManager
from gitmats.storage import StorageManager
from gitmats.metadata import MetadataManager


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
def cli_runner() -> CliRunner:
    """Create a Click CLI runner."""
    return CliRunner()


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


# ===== Basic CLI Tests =====

class TestCLIBasics:
    """Tests for basic CLI functionality."""
    
    def test_version(self, cli_runner: CliRunner):
        """Test --version flag."""
        result = cli_runner.invoke(gmt, ["--version"])
        assert result.exit_code == 0
        assert "gmt, version 0.1.0" in result.output
    
    def test_help(self, cli_runner: CliRunner):
        """Test --help flag."""
        result = cli_runner.invoke(gmt, ["--help"])
        assert result.exit_code == 0
        assert "GitMats" in result.output
        assert "Virtual workspace manager" in result.output
    
    def test_no_args(self, cli_runner: CliRunner):
        """Test running with no args shows help (or returns error)."""
        result = cli_runner.invoke(gmt)
        # Click groups return exit code 2 when invoked without subcommand
        # This is expected behavior - user needs to specify a command
        assert result.exit_code in [0, 2]


# ===== Create Command Tests =====

class TestCreateCommand:
    """Tests for 'gmt create' command."""
    
    def test_create_workspace_basic(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test basic workspace creation."""
        # Set up environment with temp config
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(
            gmt,
            ["create", "test-workspace", str(non_git_original)],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "Created workspace 'test-workspace'" in result.output
    
    def test_create_workspace_with_lock(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test workspace creation with lock option."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(
            gmt,
            ["create", "test-locked", str(non_git_original), "--lock"],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "LOCKED" in result.output
    
    def test_create_workspace_invalid_path(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
    ):
        """Test creating workspace with invalid path."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(
            gmt,
            ["create", "test-invalid", "/nonexistent/path"],
            env=env,
        )
        
        assert result.exit_code == 2  # Click validation error
    
    def test_create_workspace_duplicate_id(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test creating workspace with duplicate ID."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create first workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-duplicate", str(non_git_original)],
            env=env,
        )
        
        # Try to create duplicate
        result = cli_runner.invoke(
            gmt,
            ["create", "test-duplicate", str(non_git_original)],
            env=env,
        )
        
        assert result.exit_code == 1
        assert "already exists" in result.output


# ===== List Command Tests =====

class TestListCommand:
    """Tests for 'gmt list' command."""
    
    def test_list_empty(self, cli_runner: CliRunner, temp_config: GitMatsConfig):
        """Test listing when no workspaces."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(gmt, ["list"], env=env)
        
        assert result.exit_code == 0
        assert "No workspaces found" in result.output
    
    def test_list_workspaces(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test listing workspaces."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspaces
        cli_runner.invoke(
            gmt,
            ["create", "test-list-1", str(non_git_original)],
            env=env,
        )
        cli_runner.invoke(
            gmt,
            ["create", "test-list-2", str(non_git_original)],
            env=env,
        )
        
        # List
        result = cli_runner.invoke(gmt, ["list"], env=env)
        
        assert result.exit_code == 0
        assert "test-list-1" in result.output
        assert "test-list-2" in result.output
    
    def test_list_json_output(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test listing with JSON output."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-json", str(non_git_original)],
            env=env,
        )
        
        # List with JSON
        result = cli_runner.invoke(gmt, ["list", "--json"], env=env)
        
        assert result.exit_code == 0
        
        # Parse JSON
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["workspace_id"] == "test-json"


# ===== Status Command Tests =====

class TestStatusCommand:
    """Tests for 'gmt status' command."""
    
    def test_status_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test showing workspace status."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-status", str(non_git_original)],
            env=env,
        )
        
        # Show status
        result = cli_runner.invoke(gmt, ["status", "test-status"], env=env)
        
        assert result.exit_code == 0
        assert "test-status" in result.output
        assert "Statistics:" in result.output
    
    def test_status_nonexistent(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
    ):
        """Test status for nonexistent workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(gmt, ["status", "nonexistent"], env=env)
        
        assert result.exit_code == 1
        assert "not found" in result.output


# ===== Destroy Command Tests =====

class TestDestroyCommand:
    """Tests for 'gmt destroy' command."""
    
    def test_destroy_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test destroying workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-destroy", str(non_git_original)],
            env=env,
        )
        
        # Destroy
        result = cli_runner.invoke(gmt, ["destroy", "test-destroy"], env=env)
        
        assert result.exit_code == 0
        assert "Destroyed workspace 'test-destroy'" in result.output
    
    def test_destroy_locked_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test destroying locked workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create and lock workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-locked-destroy", str(non_git_original)],
            env=env,
        )
        cli_runner.invoke(gmt, ["lock", "test-locked-destroy"], env=env)
        
        # Destroy without force - should fail
        result = cli_runner.invoke(
            gmt,
            ["destroy", "test-locked-destroy"],
            env=env,
        )
        assert result.exit_code == 1
        
        # Destroy with force
        result = cli_runner.invoke(
            gmt,
            ["destroy", "test-locked-destroy", "--force"],
            env=env,
        )
        assert result.exit_code == 0
    
    def test_destroy_nonexistent(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
    ):
        """Test destroying nonexistent workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(gmt, ["destroy", "nonexistent"], env=env)
        
        assert result.exit_code == 1
        assert "not found" in result.output


# ===== Lock/Unlock Command Tests =====

class TestLockUnlockCommands:
    """Tests for 'gmt lock' and 'gmt unlock' commands."""
    
    def test_lock_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test locking workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-lock-cmd", str(non_git_original)],
            env=env,
        )
        
        # Lock
        result = cli_runner.invoke(gmt, ["lock", "test-lock-cmd"], env=env)
        
        assert result.exit_code == 0
        assert "Locked workspace 'test-lock-cmd'" in result.output
    
    def test_unlock_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test unlocking workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create and lock workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-unlock-cmd", str(non_git_original)],
            env=env,
        )
        cli_runner.invoke(gmt, ["lock", "test-unlock-cmd"], env=env)
        
        # Unlock
        result = cli_runner.invoke(gmt, ["unlock", "test-unlock-cmd"], env=env)
        
        assert result.exit_code == 0
        assert "Unlocked workspace 'test-unlock-cmd'" in result.output


# ===== Files Command Tests =====

class TestFilesCommand:
    """Tests for 'gmt files' command."""
    
    def test_list_files(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test listing files in workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-files", str(non_git_original)],
            env=env,
        )
        
        # List files
        result = cli_runner.invoke(gmt, ["files", "test-files"], env=env)
        
        assert result.exit_code == 0
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
    
    def test_list_files_filter_status(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test listing files filtered by status."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-files-filter", str(non_git_original)],
            env=env,
        )
        
        # List linked files
        result = cli_runner.invoke(
            gmt,
            ["files", "test-files-filter", "--status", "linked"],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "linked" in result.output


# ===== Config Command Tests =====

class TestConfigCommands:
    """Tests for 'gmt config' commands."""
    
    def test_config_show(self, cli_runner: CliRunner, temp_config: GitMatsConfig):
        """Test showing configuration."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(gmt, ["config", "show"], env=env)
        
        assert result.exit_code == 0
        assert "Current configuration:" in result.output
    
    def test_config_set_invalid_key(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
    ):
        """Test setting invalid config key."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        result = cli_runner.invoke(
            gmt,
            ["config", "set", "invalid_key", "value"],
            env=env,
        )
        
        assert result.exit_code == 1
        assert "Invalid config key" in result.output


# ===== Internal Command Tests =====

class TestInternalCommands:
    """Tests for 'gmt internal' commands."""
    
    def test_internal_validate(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test internal validate command."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-validate-internal", str(non_git_original)],
            env=env,
        )
        
        # Validate
        result = cli_runner.invoke(
            gmt,
            ["internal", "validate", "test-validate-internal"],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "valid" in result.output
    
    def test_internal_update_metadata(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test internal update-metadata command."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-update-meta", str(non_git_original)],
            env=env,
        )
        
        # Update metadata
        result = cli_runner.invoke(
            gmt,
            ["internal", "update-metadata", "test-update-meta"],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "Updated metadata" in result.output


# ===== Prune Command Tests =====

class TestPruneCommand:
    """Tests for 'gmt prune' command."""
    
    def test_prune_preview(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test prune preview (without --force)."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create and destroy workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-prune-preview", str(non_git_original)],
            env=env,
        )
        cli_runner.invoke(gmt, ["destroy", "test-prune-preview"], env=env)
        
        # Preview prune
        result = cli_runner.invoke(gmt, ["prune"], env=env)
        
        assert result.exit_code == 0
        assert "Would prune" in result.output
        assert "test-prune-preview" in result.output
    
    def test_prune_force(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test prune with --force."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create and destroy workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-prune-force", str(non_git_original)],
            env=env,
        )
        cli_runner.invoke(gmt, ["destroy", "test-prune-force"], env=env)
        
        # Force prune
        result = cli_runner.invoke(gmt, ["prune", "--force"], env=env)
        
        assert result.exit_code == 0
        assert "Pruned" in result.output


# ===== Diff Command Tests =====

class TestDiffCommand:
    """Tests for 'gmt diff' command."""
    
    def test_diff_no_changes(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
    ):
        """Test diff with no changes."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-diff-no-change", str(non_git_original)],
            env=env,
        )
        
        # Show diff
        result = cli_runner.invoke(gmt, ["diff", "test-diff-no-change"], env=env)
        
        assert result.exit_code == 0
        assert "No changes" in result.output


# ===== Export Command Tests =====

class TestExportCommand:
    """Tests for 'gmt export' command."""
    
    def test_export_workspace(
        self,
        cli_runner: CliRunner,
        temp_config: GitMatsConfig,
        non_git_original: Path,
        temp_dir: Path,
    ):
        """Test exporting workspace."""
        env = {
            "GITMATS_WORKSPACE_DIR": temp_config.default_workspace_dir,
            "GITMATS_REGISTRY_DB": temp_config.registry_db,
        }
        
        # Create workspace
        cli_runner.invoke(
            gmt,
            ["create", "test-export", str(non_git_original)],
            env=env,
        )
        
        # Export
        export_path = temp_dir / "exported"
        result = cli_runner.invoke(
            gmt,
            ["export", "test-export", str(export_path)],
            env=env,
        )
        
        assert result.exit_code == 0
        assert "Exported workspace" in result.output
        assert export_path.exists()