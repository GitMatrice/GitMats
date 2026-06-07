"""
Local Git backend for GitMats.

Provides Git integration for workspaces with:
- Inherited mode: Share Git with original via worktree
- Standalone mode: Independent Git repository
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from gitmats.config import GitMatsConfig
from gitmats.git.utils import (
    is_git_repo,
    get_git_root,
    get_git_dir,
    get_current_branch,
    get_current_head,
    get_commit_info,
    get_commit_stats,
    init_repo,
    add_worktree,
    remove_worktree,
    create_branch,
    checkout_branch,
    stage_files,
    commit,
    get_staged_files,
    get_modified_files,
    get_untracked_files,
    hash_object,
)
from gitmats.models import (
    Workspace,
    WorkspaceType,
    GitMode,
    GitCommit,
    CommitType,
    WorkspaceConfig,
    OperationLog,
    OperationType,
)
from gitmats.metadata import MetadataManager
from gitmats.storage import StorageManager


class LocalGitBackend:
    """
    Local Git backend for version control.
    
    Supports two modes:
    1. Inherited: Use Git worktree to share repo with original
    2. Standalone: Independent Git repository in workspace
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        metadata_manager: MetadataManager,
        config: Optional[GitMatsConfig] = None,
    ):
        """
        Initialize Git backend.
        
        Args:
            storage_manager: Storage manager.
            metadata_manager: Metadata manager.
            config: Optional GitMats config.
        """
        self.storage_manager = storage_manager
        self.metadata_manager = metadata_manager
        self.config = config or GitMatsConfig()
    
    def detect_workspace_type(self, original_path: str) -> WorkspaceType:
        """
        Detect workspace type based on original directory.
        
        Args:
            original_path: Path to original directory.
        
        Returns:
            WorkspaceType (INHERITED if has Git, STANDALONE otherwise).
        """
        original = Path(original_path)
        
        if is_git_repo(original):
            return WorkspaceType.INHERITED
        return WorkspaceType.STANDALONE
    
    def setup_git(
        self,
        workspace: Workspace,
        branch_name: Optional[str] = None,
    ) -> bool:
        """
        Set up Git for a workspace.
        
        Args:
            workspace: Workspace to set up Git for.
            branch_name: Optional branch name for inherited mode.
        
        Returns:
            True if successful.
        """
        if workspace.git_mode == GitMode.INHERITED:
            return self._setup_inherited(workspace, branch_name)
        else:
            return self._setup_standalone(workspace)
    
    def _setup_inherited(
        self,
        workspace: Workspace,
        branch_name: Optional[str] = None,
    ) -> bool:
        """
        Set up inherited Git (worktree).
        
        Args:
            workspace: Workspace.
            branch_name: Optional branch name.
        
        Returns:
            True if successful.
        """
        original_root = get_git_root(Path(workspace.original_path))
        if not original_root:
            return False
        
        original_git_dir = get_git_dir(original_root)
        if not original_git_dir:
            return False
        
        workspace_dir = Path(workspace.workspace_dir)
        git_dir = Path(workspace.git_dir)
        
        # Create branch for workspace if specified
        current_branch = get_current_branch(original_root) or "main"
        workspace_branch = branch_name or f"gitmats-{workspace.workspace_id}"
        
        # Create branch from current state
        create_branch(original_root, workspace_branch)
        
        # Add worktree
        success = add_worktree(
            main_repo_path=original_root,
            worktree_path=workspace_dir,
            branch=workspace_branch,
        )
        
        if success:
            # Update workspace Git info
            workspace.git_branch = workspace_branch
            workspace.git_head = get_current_head(workspace_dir)
            self.metadata_manager.update_workspace(workspace)
            
            # Record operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace.workspace_id,
                operation_type=OperationType.GIT_BRANCH,
                relative_path=None,
                timestamp=datetime.now(),
                success=True,
                details_json=f'{{"branch": "{workspace_branch}", "mode": "inherited"}}',
            ))
            
            return True
        
        return False
    
    def _setup_standalone(self, workspace: Workspace) -> bool:
        """
        Set up standalone Git repository.
        
        Args:
            workspace: Workspace.
        
        Returns:
            True if successful.
        """
        workspace_dir = Path(workspace.workspace_dir)
        git_dir = Path(workspace.git_dir)
        
        # Initialize new repository
        success = init_repo(workspace_dir)
        
        if success:
            # Create initial commit (empty)
            self._create_base_commit(workspace)
            
            # Update workspace info
            workspace.git_branch = get_current_branch(workspace_dir) or "main"
            workspace.git_head = get_current_head(workspace_dir)
            self.metadata_manager.update_workspace(workspace)
            
            return True
        
        return False
    
    def _create_base_commit(self, workspace: Workspace) -> Optional[str]:
        """
        Create base commit for standalone workspace.
        
        Args:
            workspace: Workspace.
        
        Returns:
            Commit SHA, or None if failed.
        """
        workspace_dir = Path(workspace.workspace_dir)
        
        # Configure Git identity for commit
        try:
            import subprocess
            subprocess.run(
                ["git", "config", "user.email", "gitmats@example.com"],
                cwd=workspace_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "GitMats"],
                cwd=workspace_dir,
                check=True,
            )
        except subprocess.CalledProcessError:
            pass
        
        # Create empty commit
        # Allow empty commits for base
        result = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "GitMats: Base commit (workspace created)"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
        
        sha = get_current_head(workspace_dir) if result.returncode == 0 else None
        
        if sha:
            # Record commit
            commit_info = get_commit_info(workspace_dir, sha)
            files_changed, insertions, deletions = get_commit_stats(workspace_dir, sha)
            
            git_commit = GitCommit(
                workspace_id=workspace.workspace_id,
                commit_sha=sha,
                commit_message=commit_info["commit_message"],
                tree_sha=commit_info["tree_sha"],
                parent_sha=commit_info["parent_sha"],
                author_name=commit_info["author_name"],
                author_email=commit_info["author_email"],
                authored_at=datetime.fromtimestamp(commit_info["authored_at"]),
                committer_name=commit_info["committer_name"],
                committer_email=commit_info["committer_email"],
                committed_at=datetime.fromtimestamp(commit_info["committed_at"]),
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
                commit_type=CommitType.BASE,
            )
            
            self.metadata_manager.record_commit(git_commit)
            
            return sha
        
        return None
    
    def stage_cow_files(self, workspace: Workspace) -> list[str]:
        """
        Stage all COW (modified/new) files.
        
        Args:
            workspace: Workspace.
        
        Returns:
            List of staged file paths.
        """
        workspace_dir = Path(workspace.workspace_dir)
        
        # Get all file states
        from gitmats.models import FileStatus
        
        copied_states = self.metadata_manager.list_file_states(
            workspace.workspace_id,
            status=FileStatus.COPIED,
        )
        new_states = self.metadata_manager.list_file_states(
            workspace.workspace_id,
            status=FileStatus.NEW,
        )
        
        files_to_stage = []
        
        for state in copied_states + new_states:
            files_to_stage.append(state.relative_path)
        
        if files_to_stage:
            stage_files(workspace_dir, files_to_stage)
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace.workspace_id,
                operation_type=OperationType.GIT_ADD,
                relative_path=None,
                timestamp=datetime.now(),
                success=True,
                details_json=f'{{"files": {len(files_to_stage)}}}',
            ))
        
        return files_to_stage
    
    def create_commit(
        self,
        workspace: Workspace,
        message: str,
        author: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a commit in workspace.
        
        Args:
            workspace: Workspace.
            message: Commit message.
            author: Optional author string.
        
        Returns:
            Commit SHA, or None if failed.
        """
        workspace_dir = Path(workspace.workspace_dir)
        
        # Apply commit prefix if configured
        if workspace.config.commit_prefix:
            message = f"{workspace.config.commit_prefix} {message}"
        
        sha = commit(workspace_dir, message, author)
        
        if sha:
            # Record commit
            commit_info = get_commit_info(workspace_dir, sha)
            files_changed, insertions, deletions = get_commit_stats(workspace_dir, sha)
            
            git_commit = GitCommit(
                workspace_id=workspace.workspace_id,
                commit_sha=sha,
                commit_message=commit_info["commit_message"],
                tree_sha=commit_info["tree_sha"],
                parent_sha=commit_info["parent_sha"],
                author_name=commit_info["author_name"],
                author_email=commit_info["author_email"],
                authored_at=datetime.fromtimestamp(commit_info["authored_at"]),
                committer_name=commit_info["committer_name"],
                committer_email=commit_info["committer_email"],
                committed_at=datetime.fromtimestamp(commit_info["committed_at"]),
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
                commit_type=CommitType.USER,
            )
            
            self.metadata_manager.record_commit(git_commit)
            
            # Update workspace HEAD
            workspace.git_head = sha
            self.metadata_manager.update_workspace(workspace)
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace.workspace_id,
                operation_type=OperationType.GIT_COMMIT,
                relative_path=None,
                timestamp=datetime.now(),
                success=True,
                details_json=f'{{"sha": "{sha}"}}',
            ))
            
            return sha
        
        return None
    
    def get_status(self, workspace: Workspace) -> dict:
        """
        Get Git status for workspace.
        
        Args:
            workspace: Workspace.
        
        Returns:
            Dictionary with status information.
        """
        workspace_dir = Path(workspace.workspace_dir)
        
        return {
            "branch": get_current_branch(workspace_dir),
            "head": get_current_head(workspace_dir),
            "staged": get_staged_files(workspace_dir),
            "modified": get_modified_files(workspace_dir),
            "untracked": get_untracked_files(workspace_dir),
        }
    
    def create_branch(
        self,
        workspace: Workspace,
        branch_name: str,
        start_point: Optional[str] = None,
    ) -> bool:
        """
        Create a new branch in workspace.
        
        Args:
            workspace: Workspace.
            branch_name: Branch name.
            start_point: Optional starting commit.
        
        Returns:
            True if successful.
        """
        workspace_dir = Path(workspace.workspace_dir)
        
        success = create_branch(workspace_dir, branch_name, start_point)
        
        if success:
            checkout_branch(workspace_dir, branch_name)
            
            # Update workspace
            workspace.git_branch = branch_name
            workspace.git_head = get_current_head(workspace_dir)
            self.metadata_manager.update_workspace(workspace)
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace.workspace_id,
                operation_type=OperationType.GIT_BRANCH,
                relative_path=None,
                timestamp=datetime.now(),
                success=True,
                details_json=f'{{"branch": "{branch_name}"}}',
            ))
            
            return True
        
        return False
    
    def cleanup_git(self, workspace: Workspace) -> bool:
        """
        Clean up Git for workspace destruction.
        
        Args:
            workspace: Workspace.
        
        Returns:
            True if successful.
        """
        if workspace.git_mode == GitMode.INHERITED:
            return self._cleanup_inherited(workspace)
        else:
            return self._cleanup_standalone(workspace)
    
    def _cleanup_inherited(self, workspace: Workspace) -> bool:
        """
        Clean up inherited Git (remove worktree).
        
        Args:
            workspace: Workspace.
        
        Returns:
            True if successful.
        """
        original_root = get_git_root(Path(workspace.original_path))
        if not original_root:
            return True  # Original gone, nothing to clean
        
        workspace_dir = Path(workspace.workspace_dir)
        
        # Remove worktree
        success = remove_worktree(original_root, workspace_dir, force=True)
        
        # Optionally delete branch
        if workspace.git_branch:
            try:
                import subprocess
                subprocess.run(
                    ["git", "branch", "-D", workspace.git_branch],
                    cwd=original_root,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                pass
        
        return success
    
    def _cleanup_standalone(self, workspace: Workspace) -> bool:
        """
        Clean up standalone Git.
        
        Args:
            workspace: Workspace.
        
        Returns:
            True (no special cleanup needed).
        """
        # Standalone Git is in workspace, destroyed with workspace
        return True
    
    def install_hooks(self, workspace: Workspace) -> bool:
        """
        Install Git hooks for workspace.
        
        Args:
            workspace: Workspace.
        
        Returns:
            True if successful.
        """
        if not workspace.config.hooks_enabled:
            return True
        
        hooks_dir = Path(workspace.git_dir) / "hooks"
        
        # Create post-commit hook for tracking
        post_commit_hook = hooks_dir / "post-commit"
        hook_content = '''#!/bin/sh
# GitMats post-commit hook
# Records commit in GitMats metadata

echo "GitMats: commit recorded"
'''
        
        try:
            post_commit_hook.write_text(hook_content)
            post_commit_hook.chmod(0o755)
            return True
        except Exception:
            return False
    
    def sync_to_original(self, workspace: Workspace) -> bool:
        """
        Sync changes back to original (inherited mode).
        
        Args:
            workspace: Workspace.
        
        Returns:
            True if successful.
        """
        if workspace.git_mode != GitMode.INHERITED:
            return False
        
        original_root = get_git_root(Path(workspace.original_path))
        if not original_root:
            return False
        
        workspace_dir = Path(workspace.workspace_dir)
        workspace_branch = workspace.git_branch
        
        if not workspace_branch:
            return False
        
        # Checkout original branch and merge
        try:
            import subprocess
            
            # Get current original branch
            original_branch = get_current_branch(original_root) or "main"
            
            # Checkout original
            subprocess.run(
                ["git", "checkout", original_branch],
                cwd=original_root,
                check=True,
                capture_output=True,
            )
            
            # Merge workspace branch
            subprocess.run(
                ["git", "merge", workspace_branch],
                cwd=original_root,
                check=True,
                capture_output=True,
            )
            
            # Log operation
            self.metadata_manager.log_operation(OperationLog(
                workspace_id=workspace.workspace_id,
                operation_type=OperationType.GIT_SYNC,
                relative_path=None,
                timestamp=datetime.now(),
                success=True,
                details_json=f'{{"branch": "{workspace_branch}", "to": "original"}}',
            ))
            
            return True
        except subprocess.CalledProcessError:
            return False