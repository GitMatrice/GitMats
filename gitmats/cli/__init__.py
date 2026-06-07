"""
GitMats CLI - Command-line interface for virtual workspace management.

Provides commands for:
- Workspace management (create, list, status, destroy, prune)
- Version control (commit, diff, log, branch, sync)
- File management (files, reset, export)
- Configuration (config set, config show)
- Internal maintenance (sync-cow, update-metadata, validate)
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click

from gitmats import (
    Workspace,
    WorkspaceConfig,
    WorkspaceStatus,
    WorkspaceType,
    GitMode,
    FileStatus,
    GitMatsConfig,
    MetadataManager,
    StorageManager,
    COWEngine,
    LocalGitBackend,
    WorkspaceManager,
)


# Colors for output
COLORS = {
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def color(text: str, color_name: str) -> str:
    """Apply color to text."""
    return f"{COLORS.get(color_name, '')}{text}{COLORS['reset']}"


def get_workspace_manager(config: Optional[GitMatsConfig] = None) -> WorkspaceManager:
    """Get a WorkspaceManager instance."""
    if config is None:
        config = GitMatsConfig()
    
    storage_manager = StorageManager(config)
    metadata_manager = MetadataManager(storage_manager.registry_db)
    
    return WorkspaceManager(
        config=config,
        storage_manager=storage_manager,
        metadata_manager=metadata_manager,
    )


@click.group()
@click.version_option(version="0.1.0", prog_name="gmt")
@click.option("--config", "-c", type=click.Path(), help="Path to config file")
@click.pass_context
def gmt(ctx: click.Context, config: Optional[str]) -> None:
    """GitMats - Virtual workspace manager with zero-disk overhead."""
    ctx.ensure_object(dict)
    
    gitmats_config = GitMatsConfig()
    
    # Check for environment variables (for test isolation)
    import os
    if os.environ.get("GITMATS_WORKSPACE_DIR"):
        gitmats_config.default_workspace_dir = os.environ["GITMATS_WORKSPACE_DIR"]
    if os.environ.get("GITMATS_REGISTRY_DB"):
        gitmats_config.registry_db = os.environ["GITMATS_REGISTRY_DB"]
    
    if config:
        config_path = Path(config)
        if config_path.exists():
            # TODO: Implement config file loading
            pass
    
    ctx.obj["config"] = gitmats_config
    ctx.obj["manager"] = get_workspace_manager(gitmats_config)


# ===== Workspace Commands =====

@gmt.command("create")
@click.argument("workspace_id")
@click.argument("original_path", type=click.Path(exists=True))
@click.option("--branch", "-b", help="Branch name for workspace")
@click.option("--lock", "-l", is_flag=True, help="Lock workspace after creation")
@click.option("--auto-commit", is_flag=True, help="Enable auto-commit")
@click.option("--sync-on-destroy", is_flag=True, help="Sync changes on destroy")
@click.pass_context
def create_workspace(
    ctx: click.Context,
    workspace_id: str,
    original_path: str,
    branch: Optional[str],
    lock: bool,
    auto_commit: bool,
    sync_on_destroy: bool,
) -> None:
    """Create a new virtual workspace.
    
    WORKSPACE_ID: Unique identifier for the workspace
    ORIGINAL_PATH: Path to the original directory/repository
    """
    manager: WorkspaceManager = ctx.obj["manager"]
    
    # Build workspace config
    ws_config = WorkspaceConfig(
        auto_commit=auto_commit,
        sync_on_destroy=sync_on_destroy,
        lock_after_create=lock,
    )
    
    try:
        workspace = manager.create_workspace(
            workspace_id=workspace_id,
            original_path=original_path,
            branch_name=branch,
            workspace_config=ws_config,
        )
        
        click.echo(color(f"Created workspace '{workspace_id}'", "green"))
        click.echo(f"  Type: {workspace.workspace_type.value}")
        click.echo(f"  Git mode: {workspace.git_mode.value}")
        click.echo(f"  Location: {workspace.workspace_dir}")
        
        if workspace.git_branch:
            click.echo(f"  Branch: {workspace.git_branch}")
        
        if lock:
            click.echo(color("  Status: LOCKED", "yellow"))
        else:
            click.echo(color("  Status: ACTIVE", "green"))
        
    except ValueError as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


@gmt.command("list")
@click.option("--status", "-s", type=click.Choice(["active", "locked", "destroyed"]), help="Filter by status")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def list_workspaces(
    ctx: click.Context,
    status: Optional[str],
    output_json: bool,
) -> None:
    """List all workspaces."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    status_filter = None
    if status:
        status_filter = WorkspaceStatus(status)
    
    workspaces = manager.list_workspaces(status=status_filter)
    
    if output_json:
        data = [
            {
                "workspace_id": w.workspace_id,
                "original_path": w.original_path,
                "workspace_dir": w.workspace_dir,
                "workspace_type": w.workspace_type.value,
                "status": w.status.value,
                "git_mode": w.git_mode.value,
                "git_branch": w.git_branch,
                "created_at": w.created_at.isoformat() if w.created_at else None,
                "total_files": w.total_files,
                "linked_files": w.linked_files,
                "copied_files": w.copied_files,
            }
            for w in workspaces
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        if not workspaces:
            click.echo("No workspaces found.")
            return
        
        click.echo(f"Found {len(workspaces)} workspaces:\n")
        
        for w in workspaces:
            status_color = "green" if w.status == WorkspaceStatus.ACTIVE else "yellow" if w.status == WorkspaceStatus.LOCKED else "red"
            click.echo(f"  {color(w.workspace_id, 'bold')} [{color(w.status.value, status_color)}]")
            click.echo(f"    Original: {w.original_path}")
            click.echo(f"    Location: {w.workspace_dir}")
            click.echo(f"    Type: {w.workspace_type.value}, Git: {w.git_mode.value}")
            
            if w.git_branch:
                click.echo(f"    Branch: {w.git_branch}")
            
            click.echo(f"    Files: {w.total_files} ({w.linked_files} linked, {w.copied_files} copied)")
            click.echo()


@gmt.command("status")
@click.argument("workspace_id")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def workspace_status(
    ctx: click.Context,
    workspace_id: str,
    output_json: bool,
) -> None:
    """Show workspace status and statistics."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    # Update statistics
    stats = manager.update_statistics(workspace_id)
    
    if output_json:
        data = {
            "workspace_id": workspace.workspace_id,
            "status": workspace.status.value,
            "workspace_type": workspace.workspace_type.value,
            "git_mode": workspace.git_mode.value,
            "git_branch": workspace.git_branch,
            "git_head": workspace.git_head,
            "statistics": stats,
            "validation": manager.validate_workspace(workspace_id),
        }
        click.echo(json.dumps(data, indent=2))
    else:
        status_color = "green" if workspace.status == WorkspaceStatus.ACTIVE else "yellow" if workspace.status == WorkspaceStatus.LOCKED else "red"
        click.echo(color(f"Workspace: {workspace_id}", "bold"))
        click.echo(f"  Status: {color(workspace.status.value, status_color)}")
        click.echo(f"  Type: {workspace.workspace_type.value}")
        click.echo(f"  Git mode: {workspace.git_mode.value}")
        
        if workspace.git_branch:
            click.echo(f"  Branch: {workspace.git_branch}")
        
        if workspace.git_head:
            click.echo(f"  HEAD: {workspace.git_head[:12]}...")
        
        click.echo()
        click.echo("Statistics:")
        click.echo(f"  Total files: {stats['total_files']}")
        click.echo(f"  Linked: {stats['linked_files']}")
        click.echo(f"  Copied: {stats['copied_files']}")
        click.echo(f"  New: {stats['new_files']}")
        click.echo(f"  Deleted: {stats['deleted_files']}")
        click.echo(f"  Disk usage: {stats['disk_usage_bytes']} bytes")
        click.echo(f"  Original size: {stats['original_size_bytes']} bytes")
        click.echo(f"  Savings: {stats['savings_ratio'] * 100:.1f}%")


@gmt.command("destroy")
@click.argument("workspace_id")
@click.option("--force", "-f", is_flag=True, help="Force destroy even if locked")
@click.option("--sync", "-s", is_flag=True, help="Sync changes to original before destroy")
@click.pass_context
def destroy_workspace(
    ctx: click.Context,
    workspace_id: str,
    force: bool,
    sync: bool,
) -> None:
    """Destroy a workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    try:
        result = manager.destroy_workspace(workspace_id, sync=sync, force=force)
        
        if result:
            click.echo(color(f"Destroyed workspace '{workspace_id}'", "green"))
            if sync:
                click.echo("  Changes synced to original")
        else:
            click.echo(color(f"Failed to destroy workspace '{workspace_id}'", "red"), err=True)
            sys.exit(1)
        
    except ValueError as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


@gmt.command("prune")
@click.option("--force", "-f", is_flag=True, help="Actually remove destroyed workspaces")
@click.pass_context
def prune_workspaces(ctx: click.Context, force: bool) -> None:
    """Remove destroyed workspaces from registry."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    if not force:
        # Just show what would be pruned
        destroyed = manager.list_workspaces(status=WorkspaceStatus.DESTROYED)
        
        if not destroyed:
            click.echo("No destroyed workspaces to prune.")
            return
        
        click.echo(f"Would prune {len(destroyed)} destroyed workspaces:")
        for w in destroyed:
            click.echo(f"  {w.workspace_id}")
        
        click.echo()
        click.echo("Run with --force to actually prune.")
    else:
        pruned = manager.prune_workspaces()
        
        if not pruned:
            click.echo("No destroyed workspaces to prune.")
        else:
            click.echo(color(f"Pruned {len(pruned)} destroyed workspaces", "green"))
            for workspace_id in pruned:
                click.echo(f"  {workspace_id}")


# ===== Lock/Unlock Commands =====

@gmt.command("lock")
@click.argument("workspace_id")
@click.pass_context
def lock_workspace(ctx: click.Context, workspace_id: str) -> None:
    """Lock a workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    try:
        result = manager.lock_workspace(workspace_id)
        
        if result:
            click.echo(color(f"Locked workspace '{workspace_id}'", "yellow"))
        else:
            click.echo(color(f"Failed to lock workspace '{workspace_id}'", "red"), err=True)
            sys.exit(1)
        
    except ValueError as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


@gmt.command("unlock")
@click.argument("workspace_id")
@click.pass_context
def unlock_workspace(ctx: click.Context, workspace_id: str) -> None:
    """Unlock a workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    try:
        result = manager.unlock_workspace(workspace_id)
        
        if result:
            click.echo(color(f"Unlocked workspace '{workspace_id}'", "green"))
        else:
            click.echo(color(f"Failed to unlock workspace '{workspace_id}'", "red"), err=True)
            sys.exit(1)
        
    except ValueError as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


# ===== Version Control Commands =====

@gmt.command("commit")
@click.argument("workspace_id")
@click.option("--message", "-m", required=True, help="Commit message")
@click.option("--author", "-a", help="Author (Name <email>)")
@click.pass_context
def commit_changes(
    ctx: click.Context,
    workspace_id: str,
    message: str,
    author: Optional[str],
) -> None:
    """Commit changes in workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    if workspace.status != WorkspaceStatus.ACTIVE:
        click.echo(color(f"Error: Workspace '{workspace_id}' is not active", "red"), err=True)
        sys.exit(1)
    
    try:
        commit_sha = manager.git_backend.create_commit(workspace, message, author)
        
        if commit_sha:
            click.echo(color(f"Created commit {commit_sha[:12]}...", "green"))
        else:
            click.echo(color("No changes to commit", "yellow"))
        
    except Exception as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


@gmt.command("diff")
@click.argument("workspace_id")
@click.option("--original", "-o", is_flag=True, help="Diff against original")
@click.option("--last-commit", "-l", is_flag=True, help="Diff against last commit")
@click.pass_context
def show_diff(
    ctx: click.Context,
    workspace_id: str,
    original: bool,
    last_commit: bool,
) -> None:
    """Show changes in workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    # Get modified files
    states = manager.get_file_states(workspace_id)
    
    modified = [s for s in states if s.status == FileStatus.COPIED]
    new_files = [s for s in states if s.status == FileStatus.NEW]
    deleted = [s for s in states if s.status == FileStatus.DELETED]
    
    if not modified and not new_files and not deleted:
        click.echo("No changes in workspace.")
        return
    
    if modified:
        click.echo(color("Modified files:", "yellow"))
        for s in modified:
            click.echo(f"  {s.relative_path}")
    
    if new_files:
        click.echo(color("New files:", "green"))
        for s in new_files:
            click.echo(f"  {s.relative_path}")
    
    if deleted:
        click.echo(color("Deleted files:", "red"))
        for s in deleted:
            click.echo(f"  {s.relative_path}")


@gmt.command("log")
@click.argument("workspace_id")
@click.option("--limit", "-n", default=10, help="Number of commits to show")
@click.pass_context
def show_log(
    ctx: click.Context,
    workspace_id: str,
    limit: int,
) -> None:
    """Show commit history."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    if workspace.workspace_type == WorkspaceType.STANDALONE and workspace.git_mode == GitMode.STANDALONE:
        # For standalone, we can get commits using git utils
        from gitmats.git.utils import get_commit_info, get_current_head
        
        workspace_dir = Path(workspace.workspace_dir)
        head = get_current_head(workspace_dir)
        
        if not head:
            click.echo("No commits in workspace.")
            return
        
        commits = []
        current_sha = head
        
        for _ in range(limit):
            if not current_sha:
                break
            
            info = get_commit_info(workspace_dir, current_sha)
            commits.append(info)
            current_sha = info.get("parent_sha")
        
        for c in commits:
            click.echo(color(f"commit {c['commit_sha']}", "yellow"))
            click.echo(f"Author: {c['author_name']} <{c['author_email']}>")
            click.echo(f"Date: {datetime.fromtimestamp(c['authored_at']).strftime('%Y-%m-%d %H:%M:%S')}")
            click.echo()
            click.echo(f"    {c['commit_message']}")
            click.echo()
    else:
        click.echo("Git log available for standalone workspaces.")


@gmt.command("branch")
@click.argument("workspace_id")
@click.option("--create", "-c", help="Create new branch")
@click.option("--list", "-l", "list_branches", is_flag=True, help="List branches")
@click.pass_context
def manage_branch(
    ctx: click.Context,
    workspace_id: str,
    create: Optional[str],
    list_branches: bool,
) -> None:
    """Manage branches in workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    if list_branches:
        from gitmats.git.utils import get_current_branch
        
        workspace_dir = Path(workspace.workspace_dir)
        current = get_current_branch(workspace_dir)
        click.echo(f"Current branch: {color(current or 'HEAD', 'green')}")
    
    if create:
        try:
            success = manager.git_backend.create_branch(workspace, create)
            
            if success:
                click.echo(color(f"Created branch '{create}'", "green"))
            else:
                click.echo(color(f"Failed to create branch '{create}'", "red"), err=True)
                sys.exit(1)
        except Exception as e:
            click.echo(color(f"Error: {e}", "red"), err=True)
            sys.exit(1)


@gmt.command("sync")
@click.argument("workspace_id")
@click.pass_context
def sync_workspace(ctx: click.Context, workspace_id: str) -> None:
    """Sync workspace changes to original."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    if workspace.git_mode != GitMode.INHERITED:
        click.echo(color("Error: Only inherited workspaces can sync", "red"), err=True)
        sys.exit(1)
    
    try:
        success = manager.git_backend.sync_to_original(workspace)
        
        if success:
            click.echo(color(f"Synced workspace '{workspace_id}' to original", "green"))
        else:
            click.echo(color("Sync failed", "red"), err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


# ===== File Commands =====

@gmt.command("files")
@click.argument("workspace_id")
@click.option("--status", "-s", type=click.Choice(["linked", "copied", "new", "deleted"]), help="Filter by status")
@click.pass_context
def list_files(
    ctx: click.Context,
    workspace_id: str,
    status: Optional[str],
) -> None:
    """List files in workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    status_filter = None
    if status:
        status_filter = FileStatus(status)
    
    states = manager.get_file_states(workspace_id, status=status_filter)
    
    if not states:
        click.echo("No files found.")
        return
    
    for s in states:
        status_color = "green" if s.status == FileStatus.LINKED else "yellow" if s.status == FileStatus.COPIED else "cyan" if s.status == FileStatus.NEW else "red"
        click.echo(f"  [{color(s.status.value, status_color)}] {s.relative_path}")
    
    click.echo()
    click.echo(f"Total: {len(states)} files")


@gmt.command("reset")
@click.argument("workspace_id")
@click.argument("file_path", required=False)
@click.option("--all", "-a", "reset_all", is_flag=True, help="Reset all files")
@click.pass_context
def reset_file(
    ctx: click.Context,
    workspace_id: str,
    file_path: Optional[str],
    reset_all: bool,
) -> None:
    """Reset file(s) to original state."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    if reset_all:
        # Reset all copied files
        states = manager.get_file_states(workspace_id, status=FileStatus.COPIED)
        
        if not states:
            click.echo("No files to reset.")
            return
        
        reset_count = 0
        for s in states:
            try:
                manager.cow_engine.copy_down(workspace_id, s.relative_path)
                reset_count += 1
            except Exception as e:
                click.echo(color(f"Error resetting {s.relative_path}: {e}", "red"), err=True)
        
        click.echo(color(f"Reset {reset_count} files", "green"))
    
    elif file_path:
        try:
            manager.cow_engine.copy_down(workspace_id, file_path)
            click.echo(color(f"Reset '{file_path}' to original", "green"))
        except Exception as e:
            click.echo(color(f"Error: {e}", "red"), err=True)
            sys.exit(1)
    
    else:
        click.echo("Error: Specify a file path or use --all", err=True)
        sys.exit(1)


@gmt.command("export")
@click.argument("workspace_id")
@click.argument("output_path", type=click.Path())
@click.pass_context
def export_workspace(
    ctx: click.Context,
    workspace_id: str,
    output_path: str,
) -> None:
    """Export workspace changes to a directory."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    try:
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all files from workspace
        workspace_dir = Path(workspace.workspace_dir)
        
        for item in workspace_dir.iterdir():
            if item.is_symlink() or item.is_file():
                shutil.copy2(item, output_dir / item.name)
            elif item.is_dir():
                if item.name != ".git":  # Skip git directory
                    shutil.copytree(item, output_dir / item.name, dirs_exist_ok=True)
        
        click.echo(color(f"Exported workspace to '{output_path}'", "green"))
        
    except Exception as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


# ===== Configuration Commands =====

@gmt.group("config")
def config_group() -> None:
    """Manage configuration."""
    pass


@config_group.command("show")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Show current configuration."""
    config: GitMatsConfig = ctx.obj["config"]
    
    click.echo("Current configuration:")
    click.echo(f"  Default workspace directory: {config.default_workspace_dir}")
    click.echo(f"  Registry database: {config.registry_db}")


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_config(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value."""
    config: GitMatsConfig = ctx.obj["config"]
    
    valid_keys = ["default_workspace_dir", "registry_db"]
    
    if key not in valid_keys:
        click.echo(color(f"Error: Invalid config key '{key}'", "red"), err=True)
        click.echo(f"Valid keys: {', '.join(valid_keys)}")
        sys.exit(1)
    
    setattr(config, key, value)
    click.echo(color(f"Set {key} = {value}", "green"))


# ===== Internal Commands =====

@gmt.group("internal")
def internal_group() -> None:
    """Internal maintenance commands."""
    pass


@internal_group.command("validate")
@click.argument("workspace_id")
@click.pass_context
def validate_workspace(ctx: click.Context, workspace_id: str) -> None:
    """Validate workspace integrity."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    result = manager.validate_workspace(workspace_id)
    
    if result.get("valid"):
        click.echo(color(f"Workspace '{workspace_id}' is valid", "green"))
        click.echo(f"  Files checked: {result.get('file_count', 0)}")
    else:
        click.echo(color(f"Workspace '{workspace_id}' has issues", "red"))
        
        if "error" in result:
            click.echo(f"  Error: {result['error']}")
        
        for error in result.get("errors", []):
            click.echo(f"  {error}")


@internal_group.command("sync-cow")
@click.argument("workspace_id")
@click.pass_context
def sync_cow(ctx: click.Context, workspace_id: str) -> None:
    """Sync COW state for workspace."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    try:
        manager.cow_engine.sync_cow_state(workspace_id)
        click.echo(color(f"Synced COW state for '{workspace_id}'", "green"))
    except Exception as e:
        click.echo(color(f"Error: {e}", "red"), err=True)
        sys.exit(1)


@internal_group.command("update-metadata")
@click.argument("workspace_id")
@click.pass_context
def update_metadata(ctx: click.Context, workspace_id: str) -> None:
    """Update workspace metadata."""
    manager: WorkspaceManager = ctx.obj["manager"]
    
    workspace = manager.get_workspace(workspace_id)
    if not workspace:
        click.echo(color(f"Error: Workspace '{workspace_id}' not found", "red"), err=True)
        sys.exit(1)
    
    stats = manager.update_statistics(workspace_id)
    click.echo(color(f"Updated metadata for '{workspace_id}'", "green"))
    click.echo(f"  Total files: {stats['total_files']}")
    click.echo(f"  Linked: {stats['linked_files']}")
    click.echo(f"  Copied: {stats['copied_files']}")


# Main entry point
def main() -> None:
    """Main entry point for CLI."""
    gmt()


if __name__ == "__main__":
    main()