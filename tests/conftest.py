"""Test fixtures and configuration."""

import tempfile
from pathlib import Path
import pytest

from gitmats.config import GitMatsConfig
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager


@pytest.fixture
def temp_gitmats_root():
    """Create temporary GitMats root directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def gitmats_config(temp_gitmats_root):
    """Create GitMats configuration with temp paths."""
    config = GitMatsConfig()
    config.default_workspace_dir = str(temp_gitmats_root / "workspaces")
    config.registry_db = str(temp_gitmats_root / "registry.db")
    return config


@pytest.fixture
def storage_manager(gitmats_config):
    """Create StorageManager with temp config."""
    return StorageManager(gitmats_config)


@pytest.fixture
def metadata_manager(gitmats_config):
    """Create MetadataManager with temp config."""
    registry_path = gitmats_config.get_registry_db_path()
    return MetadataManager(registry_path)


@pytest.fixture
def sample_workspace(storage_manager, metadata_manager):
    """Create a sample workspace for testing."""
    from gitmats.models import Workspace, WorkspaceType, GitMode, WorkspaceStatus, WorkspaceConfig
    from datetime import datetime
    
    # Create temp original directory
    with tempfile.TemporaryDirectory() as original_dir:
        # Create some sample files
        original = Path(original_dir)
        (original / "src").mkdir()
        (original / "src" / "main.py").write_text("print('hello')")
        (original / "config.yaml").write_text("name: test")
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-workspace",
            original_path=str(original),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        
        # Register in metadata
        metadata_manager.create_workspace(workspace)
        
        yield workspace


@pytest.fixture
def sample_git_repo():
    """Create a sample Git repository for testing."""
    import subprocess
    
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        
        # Create some files
        (repo_path / "README.md").write_text("# Test Repo")
        (repo_path / "src").mkdir()
        (repo_path / "src" / "main.py").write_text("print('hello')")
        
        # Initial commit
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
        
        yield repo_path


@pytest.fixture
def sample_non_git_dir():
    """Create a sample non-Git directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dir_path = Path(tmpdir)
        
        # Create some files
        (dir_path / "data.txt").write_text("some data")
        (dir_path / "config.json").write_text("{}")
        (dir_path / "subdir").mkdir()
        (dir_path / "subdir" / "file.py").write_text("# code")
        
        yield dir_path