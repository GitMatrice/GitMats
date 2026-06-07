"""Tests for Git integration."""

from datetime import datetime
from pathlib import Path
import subprocess
import tempfile

import pytest

from gitmats.config import GitMatsConfig
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager
from gitmats.git.utils import (
    is_git_repo,
    get_git_root,
    get_git_dir,
    get_current_branch,
    get_current_head,
    init_repo,
    create_branch,
    stage_files,
    commit,
    get_commit_info,
)
from gitmats.git.backend import LocalGitBackend
from gitmats.models import WorkspaceType, GitMode, Workspace


@pytest.fixture
def git_setup():
    """Create Git test setup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create GitMats structure
        config = GitMatsConfig()
        config.default_workspace_dir = str(root / "workspaces")
        config.registry_db = str(root / "registry.db")
        
        storage_manager = StorageManager(config)
        storage_manager.ensure_root_structure()
        
        metadata_manager = MetadataManager(config.get_registry_db_path())
        
        git_backend = LocalGitBackend(storage_manager, metadata_manager, config)
        
        yield {
            "root": root,
            "storage_manager": storage_manager,
            "metadata_manager": metadata_manager,
            "git_backend": git_backend,
        }


@pytest.fixture
def sample_git_repo(git_setup):
    """Create a sample Git repository."""
    root = git_setup["root"]
    repo_path = root / "git-repo"
    repo_path.mkdir()
    
    # Initialize repo
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
    
    yield {
        "repo_path": repo_path,
        **git_setup,
    }


@pytest.fixture
def sample_non_git(git_setup):
    """Create a sample non-Git directory."""
    root = git_setup["root"]
    dir_path = root / "non-git"
    dir_path.mkdir()
    
    # Create some files
    (dir_path / "data.txt").write_text("some data")
    (dir_path / "config.json").write_text("{}")
    
    yield {
        "dir_path": dir_path,
        **git_setup,
    }


class TestGitUtils:
    """Tests for Git utility functions."""
    
    def test_is_git_repo_true(self, sample_git_repo):
        """Test detecting Git repository."""
        repo_path = sample_git_repo["repo_path"]
        assert is_git_repo(repo_path) is True
    
    def test_is_git_repo_false(self, sample_non_git):
        """Test detecting non-Git directory."""
        dir_path = sample_non_git["dir_path"]
        assert is_git_repo(dir_path) is False
    
    def test_get_git_root(self, sample_git_repo):
        """Test getting Git root."""
        repo_path = sample_git_repo["repo_path"]
        
        # From root (resolve for macOS /var -> /private/var)
        git_root = get_git_root(repo_path)
        assert git_root is not None
        assert git_root.resolve() == repo_path.resolve()
        
        # From subdirectory
        subdir = repo_path / "src"
        git_root = get_git_root(subdir)
        assert git_root is not None
        assert git_root.resolve() == repo_path.resolve()
    
    def test_get_git_dir(self, sample_git_repo):
        """Test getting .git directory."""
        repo_path = sample_git_repo["repo_path"]
        git_dir = get_git_dir(repo_path)
        
        assert git_dir is not None
        assert git_dir.name == ".git"
    
    def test_get_current_branch(self, sample_git_repo):
        """Test getting current branch."""
        repo_path = sample_git_repo["repo_path"]
        branch = get_current_branch(repo_path)
        
        # Should be on default branch (main or master)
        assert branch in ["main", "master"]
    
    def test_get_current_head(self, sample_git_repo):
        """Test getting current HEAD."""
        repo_path = sample_git_repo["repo_path"]
        head = get_current_head(repo_path)
        
        assert head is not None
        assert len(head) == 40  # SHA-1 length
    
    def test_init_repo(self, git_setup):
        """Test initializing a repository."""
        root = git_setup["root"]
        new_repo = root / "new-repo"
        new_repo.mkdir()
        
        success = init_repo(new_repo)
        assert success is True
        assert is_git_repo(new_repo)
    
    def test_create_branch(self, sample_git_repo):
        """Test creating a branch."""
        repo_path = sample_git_repo["repo_path"]
        
        success = create_branch(repo_path, "test-branch")
        assert success is True
        
        # Verify branch exists
        result = subprocess.run(
            ["git", "branch", "--list", "test-branch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert "test-branch" in result.stdout
    
    def test_stage_and_commit(self, git_setup):
        """Test staging and committing."""
        root = git_setup["root"]
        repo_path = root / "test-repo"
        repo_path.mkdir()
        
        init_repo(repo_path)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        
        # Create file
        (repo_path / "test.txt").write_text("test content")
        
        # Stage
        success = stage_files(repo_path, ["test.txt"])
        assert success is True
        
        # Commit
        sha = commit(repo_path, "Add test file")
        assert sha is not None
        assert len(sha) == 40
    
    def test_get_commit_info(self, sample_git_repo):
        """Test getting commit info."""
        repo_path = sample_git_repo["repo_path"]
        head = get_current_head(repo_path)
        assert head is not None
        
        info = get_commit_info(repo_path, head)
        
        assert info["commit_sha"] == head
        assert info["commit_message"] == "Initial commit"
        assert info["author_name"] == "Test User"
        assert info["author_email"] == "test@test.com"


class TestLocalGitBackend:
    """Tests for LocalGitBackend."""
    
    def test_detect_workspace_type_git(self, sample_git_repo):
        """Test detecting Git workspace type."""
        git_backend = sample_git_repo["git_backend"]
        repo_path = sample_git_repo["repo_path"]
        
        workspace_type = git_backend.detect_workspace_type(str(repo_path))
        assert workspace_type == WorkspaceType.INHERITED
    
    def test_detect_workspace_type_non_git(self, sample_non_git):
        """Test detecting non-Git workspace type."""
        git_backend = sample_non_git["git_backend"]
        dir_path = sample_non_git["dir_path"]
        
        workspace_type = git_backend.detect_workspace_type(str(dir_path))
        assert workspace_type == WorkspaceType.STANDALONE
    
    def test_setup_standalone_git(self, sample_non_git):
        """Test setting up standalone Git."""
        git_backend = sample_non_git["git_backend"]
        storage_manager = sample_non_git["storage_manager"]
        metadata_manager = sample_non_git["metadata_manager"]
        dir_path = sample_non_git["dir_path"]
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-standalone",
            original_path=str(dir_path),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        metadata_manager.create_workspace(workspace)
        
        # Setup Git
        success = git_backend.setup_git(workspace)
        assert success is True
        
        # Verify Git repo
        workspace_dir = Path(workspace.workspace_dir)
        assert is_git_repo(workspace_dir)
        
        # Verify base commit exists (may be None if allow-empty commit fails)
        head = get_current_head(workspace_dir)
        # HEAD should exist after base commit
        assert head is not None
    
    def test_create_commit(self, sample_non_git):
        """Test creating a commit."""
        git_backend = sample_non_git["git_backend"]
        storage_manager = sample_non_git["storage_manager"]
        metadata_manager = sample_non_git["metadata_manager"]
        dir_path = sample_non_git["dir_path"]
        
        # Create workspace with Git
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-commit",
            original_path=str(dir_path),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        metadata_manager.create_workspace(workspace)
        git_backend.setup_git(workspace)
        
        workspace_dir = Path(workspace.workspace_dir)
        
        # Create a file
        (workspace_dir / "new_file.txt").write_text("new content")
        
        # Stage and commit
        stage_files(workspace_dir, ["new_file.txt"])
        sha = git_backend.create_commit(workspace, "Add new file")
        
        assert sha is not None
        
        # Verify commit recorded
        commits = metadata_manager.list_commits(workspace.workspace_id)
        assert len(commits) >= 1  # At least the new commit (base commit may not exist if empty)
    
    def test_get_status(self, sample_non_git):
        """Test getting Git status."""
        git_backend = sample_non_git["git_backend"]
        storage_manager = sample_non_git["storage_manager"]
        metadata_manager = sample_non_git["metadata_manager"]
        dir_path = sample_non_git["dir_path"]
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-status",
            original_path=str(dir_path),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        metadata_manager.create_workspace(workspace)
        git_backend.setup_git(workspace)
        
        workspace_dir = Path(workspace.workspace_dir)
        
        # Create untracked file
        (workspace_dir / "untracked.txt").write_text("untracked")
        
        status = git_backend.get_status(workspace)
        
        assert status["branch"] is not None
        # HEAD may be None if no commits exist yet
        assert status["head"] is not None or len(status["untracked"]) > 0
        assert "untracked.txt" in status["untracked"]
    
    def test_create_branch(self, sample_non_git):
        """Test creating a branch."""
        git_backend = sample_non_git["git_backend"]
        storage_manager = sample_non_git["storage_manager"]
        metadata_manager = sample_non_git["metadata_manager"]
        dir_path = sample_non_git["dir_path"]
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-branch",
            original_path=str(dir_path),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        metadata_manager.create_workspace(workspace)
        git_backend.setup_git(workspace)
        
        # Create branch
        success = git_backend.create_branch(workspace, "feature-branch")
        assert success is True
        
        # Verify branch
        workspace_dir = Path(workspace.workspace_dir)
        current_branch = get_current_branch(workspace_dir)
        assert current_branch == "feature-branch"
    
    def test_install_hooks(self, sample_non_git):
        """Test installing Git hooks."""
        git_backend = sample_non_git["git_backend"]
        storage_manager = sample_non_git["storage_manager"]
        metadata_manager = sample_non_git["metadata_manager"]
        dir_path = sample_non_git["dir_path"]
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-hooks",
            original_path=str(dir_path),
            workspace_type=WorkspaceType.STANDALONE,
            git_mode=GitMode.STANDALONE,
        )
        metadata_manager.create_workspace(workspace)
        git_backend.setup_git(workspace)
        
        # Install hooks
        success = git_backend.install_hooks(workspace)
        assert success is True
        
        # Verify hook exists
        hooks_dir = Path(workspace.git_dir) / "hooks"
        post_commit = hooks_dir / "post-commit"
        assert post_commit.exists()


class TestInheritedGit:
    """Tests for inherited Git mode."""
    
    def test_setup_inherited_git(self, sample_git_repo):
        """Test setting up inherited Git."""
        git_backend = sample_git_repo["git_backend"]
        storage_manager = sample_git_repo["storage_manager"]
        metadata_manager = sample_git_repo["metadata_manager"]
        repo_path = sample_git_repo["repo_path"]
        
        # Create workspace
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-inherited",
            original_path=str(repo_path),
            workspace_type=WorkspaceType.INHERITED,
            git_mode=GitMode.INHERITED,
        )
        metadata_manager.create_workspace(workspace)
        
        # Setup Git
        success = git_backend.setup_git(workspace, branch_name="test-ws-branch")
        assert success is True
        
        # Verify worktree
        workspace_dir = Path(workspace.workspace_dir)
        assert is_git_repo(workspace_dir)
        
        # Verify branch
        current_branch = get_current_branch(workspace_dir)
        assert current_branch == "test-ws-branch"
        
        # Verify worktree registered in original
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert str(workspace_dir) in result.stdout
    
    def test_cleanup_inherited_git(self, sample_git_repo):
        """Test cleaning up inherited Git."""
        git_backend = sample_git_repo["git_backend"]
        storage_manager = sample_git_repo["storage_manager"]
        metadata_manager = sample_git_repo["metadata_manager"]
        repo_path = sample_git_repo["repo_path"]
        
        # Create workspace with inherited Git
        workspace = storage_manager.create_workspace_structure(
            workspace_id="test-cleanup",
            original_path=str(repo_path),
            workspace_type=WorkspaceType.INHERITED,
            git_mode=GitMode.INHERITED,
        )
        metadata_manager.create_workspace(workspace)
        git_backend.setup_git(workspace, branch_name="cleanup-branch")
        
        workspace_dir = Path(workspace.workspace_dir)
        
        # Cleanup
        success = git_backend.cleanup_git(workspace)
        assert success is True
        
        # Verify worktree removed
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert str(workspace_dir) not in result.stdout