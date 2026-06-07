"""
Git utilities for GitMats.

Provides helper functions for Git operations.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def run_git_command(
    repo_path: Path,
    args: list[str],
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a Git command in a repository.
    
    Args:
        repo_path: Path to Git repository.
        args: Git command arguments.
        capture_output: Whether to capture output.
        check: Whether to check for success.
    
    Returns:
        CompletedProcess result.
    """
    cmd = ["git"] + args
    return subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=capture_output,
        text=True,
        check=check,
    )


def is_git_repo(path: Path) -> bool:
    """
    Check if a directory is a Git repository.
    
    Args:
        path: Path to check.
    
    Returns:
        True if it's a Git repository.
    """
    try:
        result = run_git_command(path, ["rev-parse", "--is-inside-work-tree"])
        return result.stdout.strip() == "true"
    except subprocess.CalledProcessError:
        return False


def get_git_root(path: Path) -> Optional[Path]:
    """
    Get the root directory of a Git repository.
    
    Args:
        path: Path inside repository.
    
    Returns:
        Path to repository root, or None if not in a repo.
    """
    try:
        result = run_git_command(path, ["rev-parse", "--show-toplevel"])
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def get_git_dir(path: Path) -> Optional[Path]:
    """
    Get the .git directory path.
    
    Args:
        path: Path inside repository.
    
    Returns:
        Path to .git directory, or None if not in a repo.
    """
    try:
        result = run_git_command(path, ["rev-parse", "--git-dir"])
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def get_current_branch(repo_path: Path) -> Optional[str]:
    """
    Get current branch name.
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        Branch name, or None if not on a branch.
    """
    try:
        result = run_git_command(repo_path, ["branch", "--show-current"])
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def get_current_head(repo_path: Path) -> Optional[str]:
    """
    Get current HEAD commit SHA.
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        Commit SHA, or None if no commits.
    """
    try:
        result = run_git_command(repo_path, ["rev-parse", "HEAD"])
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_commit_info(repo_path: Path, commit_sha: str) -> dict:
    """
    Get detailed commit information.
    
    Args:
        repo_path: Path to repository.
        commit_sha: Commit SHA.
    
    Returns:
        Dictionary with commit details.
    """
    # Get commit message and metadata
    result = run_git_command(
        repo_path,
        ["log", "-1", "--format=%H%n%T%n%P%n%s%n%an%n%ae%n%at%n%cn%n%ce%n%ct", commit_sha],
    )
    
    lines = result.stdout.strip().split("\n")
    
    return {
        "commit_sha": lines[0],
        "tree_sha": lines[1],
        "parent_sha": lines[2] if lines[2] else None,
        "commit_message": lines[3],
        "author_name": lines[4],
        "author_email": lines[5],
        "authored_at": int(lines[6]),
        "committer_name": lines[7],
        "committer_email": lines[8],
        "committed_at": int(lines[9]),
    }


def get_commit_stats(repo_path: Path, commit_sha: str) -> Tuple[int, int, int]:
    """
    Get commit statistics (files changed, insertions, deletions).
    
    Args:
        repo_path: Path to repository.
        commit_sha: Commit SHA.
    
    Returns:
        Tuple of (files_changed, insertions, deletions).
    """
    result = run_git_command(
        repo_path,
        ["show", "--stat", "--format=", commit_sha],
    )
    
    output = result.stdout.strip()
    
    if not output:
        return (0, 0, 0)
    
    # Parse last line for stats
    lines = output.split("\n")
    for line in reversed(lines):
        if "file" in line or "files" in line:
            # Parse: "3 files changed, 10 insertions(+), 5 deletions(-)"
            parts = line.split(",")
            
            files_changed = 0
            insertions = 0
            deletions = 0
            
            for part in parts:
                part = part.strip()
                if "file" in part:
                    files_changed = int(part.split()[0])
                elif "insertion" in part:
                    insertions = int(part.split()[0])
                elif "deletion" in part:
                    deletions = int(part.split()[0])
            
            return (files_changed, insertions, deletions)
    
    return (0, 0, 0)


def init_repo(repo_path: Path, bare: bool = False) -> bool:
    """
    Initialize a new Git repository.
    
    Args:
        repo_path: Path for new repository.
        bare: Whether to create a bare repository.
    
    Returns:
        True if successful.
    """
    args = ["init"]
    if bare:
        args.append("--bare")
    
    try:
        run_git_command(repo_path, args)
        return True
    except subprocess.CalledProcessError:
        return False


def add_worktree(
    main_repo_path: Path,
    worktree_path: Path,
    branch: Optional[str] = None,
    commit: Optional[str] = None,
) -> bool:
    """
    Add a Git worktree.
    
    Args:
        main_repo_path: Path to main repository.
        worktree_path: Path for new worktree.
        branch: Branch name for worktree.
        commit: Commit to checkout (if no branch).
    
    Returns:
        True if successful.
    """
    args = ["worktree", "add", str(worktree_path)]
    
    if branch:
        args.append(branch)
    elif commit:
        args.append(commit)
    
    try:
        run_git_command(main_repo_path, args)
        return True
    except subprocess.CalledProcessError:
        return False


def remove_worktree(main_repo_path: Path, worktree_path: Path, force: bool = False) -> bool:
    """
    Remove a Git worktree.
    
    Args:
        main_repo_path: Path to main repository.
        worktree_path: Path to worktree.
        force: Force removal even with uncommitted changes.
    
    Returns:
        True if successful.
    """
    args = ["worktree", "remove", str(worktree_path)]
    if force:
        args.append("--force")
    
    try:
        run_git_command(main_repo_path, args)
        return True
    except subprocess.CalledProcessError:
        return False


def list_worktrees(repo_path: Path) -> list[dict]:
    """
    List all worktrees for a repository.
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        List of worktree info dictionaries.
    """
    result = run_git_command(repo_path, ["worktree", "list", "--porcelain"])
    
    worktrees = []
    current_worktree = {}
    
    for line in result.stdout.strip().split("\n"):
        if line.startswith("worktree "):
            if current_worktree:
                worktrees.append(current_worktree)
            current_worktree = {"path": line.split()[1]}
        elif line.startswith("HEAD "):
            current_worktree["head"] = line.split()[1]
        elif line.startswith("branch "):
            current_worktree["branch"] = line.split()[1]
    
    if current_worktree:
        worktrees.append(current_worktree)
    
    return worktrees


def create_branch(repo_path: Path, branch_name: str, start_point: Optional[str] = None) -> bool:
    """
    Create a new branch.
    
    Args:
        repo_path: Path to repository.
        branch_name: Name for new branch.
        start_point: Starting commit or branch.
    
    Returns:
        True if successful.
    """
    args = ["branch", branch_name]
    if start_point:
        args.append(start_point)
    
    try:
        run_git_command(repo_path, args)
        return True
    except subprocess.CalledProcessError:
        return False


def checkout_branch(repo_path: Path, branch_name: str) -> bool:
    """
    Checkout a branch.
    
    Args:
        repo_path: Path to repository.
        branch_name: Branch to checkout.
    
    Returns:
        True if successful.
    """
    try:
        run_git_command(repo_path, ["checkout", branch_name])
        return True
    except subprocess.CalledProcessError:
        return False


def stage_files(repo_path: Path, files: list[str]) -> bool:
    """
    Stage files for commit.
    
    Args:
        repo_path: Path to repository.
        files: List of file paths to stage.
    
    Returns:
        True if successful.
    """
    try:
        run_git_command(repo_path, ["add"] + files)
        return True
    except subprocess.CalledProcessError:
        return False


def commit(repo_path: Path, message: str, author: Optional[str] = None) -> Optional[str]:
    """
    Create a commit.
    
    Args:
        repo_path: Path to repository.
        message: Commit message.
        author: Optional author string ("Name <email>").
    
    Returns:
        Commit SHA, or None if failed.
    """
    args = ["commit", "-m", message]
    
    env = {}
    if author:
        env["GIT_AUTHOR_NAME"], env["GIT_AUTHOR_EMAIL"] = parse_author(author)
        env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
        env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, **env} if env else None,
        )
        
        # Get commit SHA
        sha_result = run_git_command(repo_path, ["rev-parse", "HEAD"])
        return sha_result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def parse_author(author: str) -> Tuple[str, str]:
    """
    Parse author string into name and email.
    
    Args:
        author: Author string like "Name <email>".
    
    Returns:
        Tuple of (name, email).
    """
    if "<" in author and ">" in author:
        name = author.split("<")[0].strip()
        email = author.split("<")[1].split(">")[0].strip()
        return (name, email)
    return (author, "unknown@example.com")


def get_staged_files(repo_path: Path) -> list[str]:
    """
    Get list of staged files.
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        List of staged file paths.
    """
    result = run_git_command(repo_path, ["diff", "--cached", "--name-only"])
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def get_modified_files(repo_path: Path) -> list[str]:
    """
    Get list of modified files (unstaged).
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        List of modified file paths.
    """
    result = run_git_command(repo_path, ["diff", "--name-only"])
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def get_untracked_files(repo_path: Path) -> list[str]:
    """
    Get list of untracked files.
    
    Args:
        repo_path: Path to repository.
    
    Returns:
        List of untracked file paths.
    """
    result = run_git_command(repo_path, ["ls-files", "--others", "--exclude-standard"])
    return result.stdout.strip().split("\n") if result.stdout.strip() else []


def get_file_blob_sha(repo_path: Path, commit_sha: str, file_path: str) -> Optional[str]:
    """
    Get blob SHA for a file at a specific commit.
    
    Args:
        repo_path: Path to repository.
        commit_sha: Commit SHA.
        file_path: Path to file.
    
    Returns:
        Blob SHA, or None if file not in commit.
    """
    try:
        result = run_git_command(repo_path, ["ls-tree", commit_sha, file_path])
        parts = result.stdout.strip().split()
        if len(parts) >= 3:
            return parts[2]  # blob SHA
    except subprocess.CalledProcessError:
        pass
    return None


def hash_object(repo_path: Path, file_path: Path) -> Optional[str]:
    """
    Hash a file object.
    
    Args:
        repo_path: Path to repository.
        file_path: Path to file.
    
    Returns:
        Object SHA, or None if failed.
    """
    try:
        result = subprocess.run(
            ["git", "hash-object", str(file_path)],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None