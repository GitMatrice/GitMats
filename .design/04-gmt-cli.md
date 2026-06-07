# GMT CLI Design

## Overview

`gmt` is a standalone CLI that provides virtual workspace management. It follows Git's CLI conventions and integrates seamlessly with existing Git workflows.

## CLI Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                    gmt Command Structure                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  gmt <command> [<args>...]                                        │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │                    Command Groups                                 │  │
│  ├─────────────────────────────────────────────────────────────────┤  │
│  │                                                                  │  │
│  │  Workspace Management:                                           │  │
│  │    create    - Create new virtual workspace                      │  │
│  │    list      - List all workspaces                               │  │
│  │    status    - Show workspace state                              │  │
│  │    destroy   - Remove workspace                                  │  │
│  │    prune     - Clean up old workspaces                           │  │
│  │                                                                  │  │
│  │  Version Control:                                                │  │
│  │    commit    - Commit changes in workspace                       │  │
│  │    diff      - Compare with original                             │  │
│  │    log       - Show workspace history                            │  │
│  │    branch    - Manage workspace branches                         │  │
│  │    sync      - Sync changes to original                          │  │
│  │                                                                  │  │
│  │  File Operations:                                                │  │
│  │    files     - List modified files                               │  │
│  │    reset     - Reset file to original                            │  │
│  │    export    - Export changes                                    │  │
│  │                                                                  │  │
│  │  Internal (Hidden):                                              │  │
│  │    internal sync-cow                                             │  │
│  │    internal update-metadata                                      │  │
│  │    internal validate                                             │  │
│  │                                                                  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

## Command Specifications

### 1. gmt create

```bash
gmt create <workspace-id> [options]

Create a new virtual workspace.

OPTIONS:
  --from=<path>           Original workspace path (default: current directory)
  --type=<type>           Workspace type: 'inherited' or 'standalone' (default: auto-detect)
  --branch=<name>         Initial branch name (default: workspace-{id}-main)
  --template=<name>       Use workspace template
  --lock                  Lock workspace after creation
  --quiet                 Suppress output
  --force                 Overwrite existing workspace

EXAMPLES:
  # Create from current directory (auto-detect Git)
  gmt create user123
  
  # Create from specific original path
  gmt create user456 --from=/projects/myapp
  
  # Force standalone mode (no Git integration)
  gmt create review-1 --from=/data/reports --type=standalone
  
  # Create with custom branch
  gmt create feature-x --branch=feature-auth

OUTPUT:
  Created workspace 'user123'
  Type: inherited (Git versioned)
  Original: /projects/myapp
  Location: ~/.gitmats/workspaces/user123/workspace
  Branch: workspace-user123-main
  Disk saved: 0 bytes (all files symlinked)
  
  To start working:
    cd ~/.gitmats/workspaces/user123/workspace
```

### 2. gmt list

```bash
gmt list [options]

List all virtual workspaces.

OPTIONS:
  --all                   Include destroyed workspaces
  --verbose               Show detailed statistics
  --porcelain             Machine-readable output
  --format=<format>       Output format: 'table', 'json', 'simple'

OUTPUT (default):
  WORKSPACE    TYPE        ORIGINAL              STATUS    DISK USAGE
  user123      inherited   /projects/myapp       active    2.5 MB (5%)
  user456      standalone  /data/reports         active    128 KB (1%)
  review-1     inherited   /projects/myapp       locked    0 bytes

OUTPUT (--verbose):
  Workspace: user123
    Type: inherited
    Original: /projects/myapp
    Created: 2025-06-06 10:30:00
    Last accessed: 2025-06-06 15:45:00
    Status: active
    Git branch: workspace-user123-main
    Files:
      Total: 245
      Linked: 232 (95%)
      Copied: 13 (5%)
      New: 0
      Deleted: 0
    Disk usage: 2.5 MB
    Original size: 50 MB
    Savings: 95%
    Commits: 3
```

### 3. gmt status

```bash
gmt status <workspace-id> [options]

Show workspace state and modifications.

OPTIONS:
  --short                 Short format (like git status --short)
  --branch                Show branch information
  --porcelain             Machine-readable output
  --files                 List all modified files

OUTPUT (default):
  On branch workspace-user123-main
  Workspace: user123
  
  Changes to be committed:
    (use "gmt reset <file>" to discard changes)
    modified:   src/auth.py
    new file:   src/new_module.py
  
  Changes not staged for commit:
    modified:   config.yaml
  
  Symlinked to original (not modified):
    232 files
  
  Disk usage: 2.5 MB (5% of original 50 MB)

OUTPUT (--short):
  M src/auth.py
  A src/new_module.py
  M config.yaml (unstaged)
```

### 4. gmt commit

```bash
gmt commit <workspace-id> [options]

Commit changes in workspace.

OPTIONS:
  -m <message>            Commit message
  -a                      Stage all modified files before commit
  --amend                 Amend previous commit
  --allow-empty           Allow empty commit
  --author=<author>       Override author

EXAMPLES:
  # Commit with message
  gmt commit user123 -m "Add authentication module"
  
  # Stage and commit all changes
  gmt commit user123 -a -m "Update configuration"
  
  # Amend previous commit
  gmt commit user123 --amend -m "Updated message"

OUTPUT:
  [workspace-user123-main a1b2c3d] Add authentication module
   2 files changed, 45 insertions(+), 12 deletions(-)
   create mode 100644 src/new_module.py
  
  Workspace stats:
    Files copied: 13
    Disk usage: 2.5 MB (5%)
```

### 5. gmt diff

```bash
gmt diff <workspace-id> [options]

Compare workspace with original state.

OPTIONS:
  --vs-original           Compare with original (default)
  --vs-base               Compare with workspace creation base
  --vs-commit=<sha>       Compare with specific commit
  --stat                  Show diffstat only
  --file=<path>           Diff specific file
  --color                 Color output

EXAMPLES:
  # Diff all changes vs original
  gmt diff user123
  
  # Diff specific file
  gmt diff user123 --file=src/auth.py
  
  # Show statistics only
  gmt diff user123 --stat

OUTPUT:
  diff --git a/src/auth.py b/src/auth.py
  index abc123..def456 100644
  --- a/src/auth.py
  +++ b/src/auth.py
  @@ -10,6 +10,15 @@
  +def authenticate(user):
  +    # New authentication logic
  +    ...
  
  src/auth.py       | 45 ++++++++++++++++++++++++++++++++++
  config.yaml       |  8 ++---
  2 files changed, 49 insertions(+), 8 deletions(-)
```

### 6. gmt files

```bash
gmt files <workspace-id> [options]

List all modified/new/deleted files in workspace.

OPTIONS:
  --modified              Only modified files
  --new                   Only new files
  --deleted               Only deleted files
  --all                   All tracked files (including linked)
  --status                Show file status
  --size                  Show file sizes

OUTPUT:
  FILE                STATUS      ORIGINAL    COW COPY    SIZE
  src/auth.py         copied      1.2 KB      2.5 KB      +1.3 KB
  src/new_module.py   new         -           500 B       +500 B
  config.yaml         copied      256 B       264 B       +8 B
  old_file.py         deleted     800 B       -           -800 B
  
  Summary:
    Modified: 2 files
    New: 1 file
    Deleted: 1 file
    Total disk usage: 3.2 KB
```

### 7. gmt reset

```bash
gmt reset <workspace-id> [<path>] [options]

Reset file(s) to original state (discard COW copy).

OPTIONS:
  --hard                  Reset all files to original
  --soft                  Keep COW copy but unstage
  <path>                  Reset specific file

EXAMPLES:
  # Reset single file
  gmt reset user123 config.yaml
  
  # Reset all files (dangerous!)
  gmt reset user123 --hard

OUTPUT:
  Reset 'config.yaml' to original state
    - Removed COW copy (264 B)
    - Restored symlink to original
    - Saved 8 B disk space
```

### 8. gmt destroy

```bash
gmt destroy <workspace-id> [options]

Remove workspace completely.

OPTIONS:
  --force                 Force destruction even with uncommitted changes
  --keep-backup           Keep backup of COW copies
  --archive               Archive workspace to tar.gz
  --dry-run               Show what would be destroyed

EXAMPLES:
  # Destroy with confirmation
  gmt destroy user123
  
  # Force destroy
  gmt destroy user123 --force
  
  # Archive before destroy
  gmt destroy user123 --archive --keep-backup

OUTPUT:
  Destroying workspace 'user123'...
  
  Files to remove:
    COW copies: 13 files (2.5 MB)
    Git objects: 45 objects (1.2 MB)
    Metadata: 1 database
  
  Original workspace unchanged: /projects/myapp
  
  Workspace 'user123' destroyed.
  Freed 3.7 MB disk space.
```

### 9. gmt sync

```bash
gmt sync <workspace-id> [options]

Sync workspace changes back to original (merge operation).

OPTIONS:
  --to=<path>             Target path (default: original)
  --branch=<name>         Target branch
  --force                 Force sync (overwrite conflicts)
  --dry-run               Show what would be synced
  --message=<msg>         Sync commit message

EXAMPLES:
  # Sync to original
  gmt sync user123
  
  # Sync to different location
  gmt sync user123 --to=/backup/myapp
  
  # Preview sync
  gmt sync user123 --dry-run

OUTPUT:
  Syncing workspace 'user123' to /projects/myapp...
  
  Checking for conflicts...
    Original has new commits since last sync
    Conflicts detected in:
      - config.yaml
  
  Options:
    1. Force sync (--force) - overwrite original changes
    2. Manual merge - resolve conflicts in workspace first
  
  Sync aborted due to conflicts.
```

### 10. gmt prune

```bash
gmt prune [options]

Clean up old/unused workspaces.

OPTIONS:
  --expire=<time>         Expire workspaces older than <time>
  --inactive=<days>       Remove workspaces inactive for <days>
  --dry-run               Show what would be pruned
  --all                   Prune all destroyed workspaces

EXAMPLES:
  # Prune workspaces inactive for 30 days
  gmt prune --inactive=30
  
  # Expire workspaces older than 2025-01-01
  gmt prune --expire=2025-01-01

OUTPUT:
  Pruning inactive workspaces (> 30 days)...
  
  Candidates:
    review-old    (inactive 45 days)    500 KB
    temp-ws       (inactive 60 days)    1.2 MB
  
  Would remove 2 workspaces, free 1.7 MB
  Use --dry-run=false to actually prune
```

## Internal Commands

### gmt internal sync-cow

```bash
gmt internal sync-cow [options]

Internal hook command: Sync COW state before Git operations.

OPTIONS:
  --pre-commit            Run as pre-commit hook
  --post-commit           Run as post-commit hook
  --workspace=<id>        Target workspace

USAGE:
  Installed as Git hook in workspace:
  .git/hooks/pre-commit:
    #!/bin/sh
    gmt internal sync-cow --pre-commit
```

### gmt internal validate

```bash
gmt internal validate <workspace-id>

Validate workspace integrity.

Checks:
  - All symlinks valid
  - Metadata consistent
  - Git refs exist
  - COW copies match metadata

OUTPUT:
  Validating workspace 'user123'...
  
  ✓ Symlinks: 245 valid
  ✓ Metadata: consistent
  ✓ Git refs: all exist
  ✓ COW copies: 13 verified
  
  Workspace valid.
```

## Implementation

### Command Dispatcher

```python
class GMTCLI:
    """
    Main CLI entry point for gmt commands.
    """
    
    COMMANDS = {
        'create': CreateCommand,
        'list': ListCommand,
        'status': StatusCommand,
        'destroy': DestroyCommand,
        'commit': CommitCommand,
        'diff': DiffCommand,
        'files': FilesCommand,
        'reset': ResetCommand,
        'sync': SyncCommand,
        'prune': PruneCommand,
        'internal': InternalCommand,
    }
    
    def main(self, args: list[str]) -> int:
        """Main entry point."""
        
        if not args:
            self.print_usage()
            return 1
        
        command = args[0]
        if command not in self.COMMANDS:
            print(f"Unknown command: {command}")
            self.print_usage()
            return 1
        
        cmd_class = self.COMMANDS[command]
        cmd = cmd_class()
        
        try:
            return cmd.run(args[1:])
        except GitMatsError as e:
            print(f"Error: {e}")
            return 1
```

### Git Subcommand Integration

```bash
# Install gmt as Git subcommand

# Option 1: Add to PATH
ln -s /usr/local/bin/gmt ~/.local/bin/gmt

# Option 2: Add to Git exec-path
cp gmt $(git --exec-path)/gmt

# Verify installation
gmt --help
```

Git automatically recognizes executables named `git-*` in its exec-path as subcommands.

### Output Formatting

```python
class OutputFormatter:
    """
    Format output for different modes.
    """
    
    def format_table(self, data: list[dict], 
                     columns: list[str]) -> str:
        """Format as ASCII table."""
        
        # Calculate column widths
        widths = {col: len(col) for col in columns}
        for row in data:
            for col in columns:
                widths[col] = max(widths[col], len(str(row.get(col, ''))))
        
        # Build table
        lines = []
        
        # Header
        header = '  '.join(col.upper().ljust(widths[col]) for col in columns)
        lines.append(header)
        lines.append('-' * len(header))
        
        # Rows
        for row in data:
            line = '  '.join(str(row.get(col, '')).ljust(widths[col]) 
                            for col in columns)
            lines.append(line)
        
        return '\n'.join(lines)
    
    def format_json(self, data: any) -> str:
        """Format as JSON."""
        return json.dumps(data, indent=2)
    
    def format_porcelain(self, data: list[dict]) -> str:
        """Format as machine-readable (tab-separated)."""
        lines = []
        for row in data:
            line = '\t'.join(str(row.get(col, '')) for col in row)
            lines.append(line)
        return '\n'.join(lines)
```

## Configuration

### gmt Config File

```yaml
# ~/.gitmats/config.yaml

# Default settings
defaults:
  workspace_dir: ~/.gitmats/workspaces
  template_dir: ~/.gitmats/templates
  
  # Auto-detect Git
  auto_detect_git: true
  
  # Default branch naming
  branch_format: "workspace-{id}-main"
  
  # Cleanup settings
  auto_prune_days: 30
  
  # Performance
  parallel_copy: true
  max_copy_workers: 4
  
  # Git settings
  git:
    auto_commit: false
    commit_template: "GitMats: {message}"
    hooks_enabled: true

# Workspace templates
templates:
  default:
    git_mode: auto
    hooks:
      pre-commit: true
      post-commit: true
  
  review:
    git_mode: standalone
    lock_after_create: true
  
  development:
    git_mode: inherited
    sync_on_destroy: true
```

### Per-Workspace Config

```yaml
# ~/.gitmats/workspaces/{id}/.gitmats.yaml

workspace_id: user123
original_path: /projects/myapp
type: inherited
created_at: 2025-06-06T10:30:00Z

# Workspace-specific overrides
settings:
  auto_sync: false
  commit_prefix: "[user123]"
  
# Hooks customization  
hooks:
  pre-commit: |
    #!/bin/sh
    # Custom pre-commit for this workspace
    gmt internal sync-cow --pre-commit
    npm run lint  # Additional workspace-specific checks
```

## Error Messages

```python
ERROR_MESSAGES = {
    'workspace_not_found': 
        "Workspace '{id}' not found. Use 'gmt list' to see available workspaces.",
    
    'workspace_already_exists':
        "Workspace '{id}' already exists. Use --force to overwrite.",
    
    'original_not_found':
        "Original path '{path}' does not exist.",
    
    'original_has_git':
        "Original '{path}' is a Git repository. Use --type=inherited.",
    
    'original_no_git':
        "Original '{path}' has no Git repository. Use --type=standalone.",
    
    'uncommitted_changes':
        "Workspace has uncommitted changes. Commit first or use --force.",
    
    'sync_conflicts':
        "Conflicts detected during sync. Resolve manually or use --force.",
    
    'disk_full':
        "Insufficient disk space for COW copy. Required: {required} MB, Available: {available} MB.",
    
    'permission_denied':
        "Permission denied for '{path}'. Check file permissions.",
    
    'symlink_failed':
        "Failed to create symlink for '{path}'. Reason: {reason}",
}
```

## Bash Completion

```bash
# ~/.bash_completion.d/gmt

_git_mats() {
    local cur prev words cword
    _init_completion || return
    
    local commands="create list status destroy commit diff files reset sync prune internal"
    
    if [ $cword -eq 2 ]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        return
    fi
    
    local command=${words[2]}
    
    case $command in
        create)
            COMPREPLY=($(compgen -W "--from --type --branch --template --lock --quiet --force" -- "$cur"))
            ;;
        list)
            COMPREPLY=($(compgen -W "--all --verbose --porcelain --format" -- "$cur"))
            ;;
        status|commit|diff|files|reset|destroy|sync)
            # Complete workspace IDs
            local workspaces=$(gmt list --porcelain | cut -f1)
            COMPREPLY=($(compgen -W "$workspaces" -- "$cur"))
            ;;
    esac
}

complete -F _git_mats gmt
```

## Man Page Structure

```
GIT-MATS(1)                    Git Manual                    GIT-MATS(1)

NAME
       gmt - Virtual workspace management with copy-on-write

SYNOPSIS
       gmt <command> [<args>...]

DESCRIPTION
       gmt provides isolated virtual workspaces that share
       files with an original directory via symlinks, using
       copy-on-write for modifications. This enables multiple
       users to work on the same codebase without duplicating
       files or modifying the original.

COMMANDS
       Workspace Management
           create, list, status, destroy, prune

       Version Control
           commit, diff, log, branch, sync

       File Operations
           files, reset, export

OPTIONS
       See individual command help: gmt <command> --help

EXAMPLES
       Create and work in a virtual workspace:
           gmt create my-work --from=/projects/app
           cd ~/.gitmats/workspaces/my-work/workspace
           # Make changes...
           gmt commit my-work -m "My changes"
           gmt sync my-work  # Sync back to original

FILES
       ~/.gitmats/
           Workspace storage and configuration

       ~/.gitmats/config.yaml
           Global configuration

       ~/.gitmats/workspaces/{id}/
           Per-workspace storage

SEE ALSO
       git-worktree(1), git(1)

GIT-MATS                        2025-06-06                   GIT-MATS(1)
```