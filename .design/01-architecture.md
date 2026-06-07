# GitMats Architecture

## High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          GitMats System                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                         GMT CLI Interface                         │ │
│  │                                                                   │ │
│  │   $ gmt create <workspace-id> [--from=<original>]                │ │
│  │   $ gmt list                                                      │ │
│  │   $ gmt status <workspace-id>                                     │ │
│  │   $ gmt commit <workspace-id> -m "message"                        │ │
│  │   $ gmt destroy <workspace-id>                                    │ │
│  │   $ gmt diff <workspace-id>                                       │ │
│  │   $ gmt sync <workspace-id> [--to=<original>]                     │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    Workspace Manager                              │ │
│  │                                                                   │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │ │
│  │  │ Workspace   │ │ Git Engine  │ │ COW Engine  │ │ Metadata  │ │ │
│  │  │ Factory     │ │             │ │             │ │ Manager   │ │ │
│  │  │             │ │ - worktree  │ │ - symlink   │ │           │ │ │
│  │  │ - create    │ │ - alternates│ │   mgmt      │ │ - SQLite  │ │ │
│  │  │ - destroy   │ │ - refs      │ │ - copy_up   │ │ - state   │ │ │
│  │  │ - lifecycle │ │ - index     │ │ - tracking  │ │   tracking│ │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│            ┌─────────────────┴─────────────────┐                       │
│            │                                   │                        │
│            ▼                                   ▼                        │
│  ┌──────────────────────┐       ┌──────────────────────────────────┐ │
│  │   Original Workspace │       │   Virtual Workspace Storage      │ │
│  │   (Read-Only Base)   │       │                                  │ │
│  │                      │       │   ~/.gitmats/                    │ │
│  │   /original/         │       │   ├── workspaces/               │ │
│  │   ├── .git/          │◄──────│   │   ├── user123/              │ │
│  │   │   ├── objects/   │ alt   │   │   │   ├── workspace/        │ │
│  │   │   ├── refs/      │ obj   │   │   │   ├── git/              │ │
│  │   │   └── worktrees/ │       │   │   │   ├── copies/           │ │
│  │   ├── src/           │ symlink│   │   │   └── metadata.db      │ │
│  │   ├── images/        │──────►│   │   └── user456/              │ │
│  │   └── config.yaml    │       │   │       └── ...               │ │
│  │                      │       │   ├── registry.db               │ │
│  │                      │       │   └── templates/                │ │
│  └──────────────────────┘       └──────────────────────────────────┘ │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. CLI Layer (gmt)

Extends Git conventions with workspace management commands:

```bash
# Standard Git commands still work in virtual workspace
cd ~/.gitmats/workspaces/user123/workspace
git status              # Shows uncommitted COW changes
git add -A
git commit -m "changes"
git log                 # Shows commits in this workspace

# GMT provides workspace-level operations
gmt create user123 --from=/original
gmt status user123
gmt commit user123 -m "checkpoint"
gmt diff user123 --vs-original
gmt destroy user123
```

### 2. Workspace Manager

Core orchestration component:

```python
class WorkspaceManager:
    """
    Central manager for all virtual workspaces.
    
    Responsibilities:
    - Workspace creation and destruction
    - Git integration setup
    - COW engine initialization
    - Metadata persistence
    """
    
    def create_workspace(self, workspace_id: str, 
                         original_path: str,
                         workspace_type: str = 'auto') -> Workspace:
        """
        Create a new virtual workspace.
        
        Args:
            workspace_id: Unique identifier for workspace
            original_path: Path to original workspace
            workspace_type: 'inherited' (git versioned) or 'standalone'
        
        Returns:
            Workspace object ready for use
        """
        
    def detect_workspace_type(self, original_path: str) -> str:
        """Detect if original has Git repository"""
        git_dir = Path(original_path) / '.git'
        if git_dir.exists():
            return 'inherited'
        return 'standalone'
```

### 3. Git Engine

Handles all Git-related operations:

```python
class GitEngine:
    """
    Git integration for virtual workspaces.
    
    Two modes:
    - Inherited: Share objects with original, use worktree-like structure
    - Standalone: Independent git repository tracking COW changes
    """
    
    # ===== Inherited Mode (Original has Git) =====
    
    def setup_inherited_git(self, workspace: Workspace) -> None:
        """
        Setup Git for inherited workspace.
        
        Strategy: Git worktree + alternates + custom refs
        
        1. Create linked worktree entry in original's .git/worktrees/
        2. Create workspace-specific:
           - HEAD (pointing to original HEAD or new branch)
           - index (staging area)
           - config.worktree (per-worktree config)
        3. Share object database with original (alternates)
        4. Create git-mats/* refs for tracking COW state
        """
        
    def create_virtual_worktree(self, original_git_dir: Path,
                                 workspace_id: str,
                                 worktree_path: Path) -> GitWorktree:
        """
        Create a virtual worktree entry.
        
        Structure:
        original/.git/worktrees/gitmats-{workspace_id}/
            ├── gitdir       -> points to workspace git dir
            ├── HEAD         -> workspace HEAD (branch)
            ├── index        -> workspace index file
            ├── config.worktree -> per-worktree config
            └── commondir    -> link to original commondir
        """
        
    def create_cow_refs(self, workspace: Workspace) -> None:
        """
        Create git-mats/* refs to track COW state.
        
        Refs created:
        refs/gitmats/{workspace_id}/base      -> Original HEAD at creation
        refs/gitmats/{workspace_id}/cow-base  -> Last synced with original
        refs/gitmats/{workspace_id}/head      -> Current workspace state
        
        These refs exist in the shared ref namespace but are prefixed
        to avoid conflicts with normal user refs.
        """
    
    # ===== Standalone Mode (Original has no Git) =====
    
    def setup_standalone_git(self, workspace: Workspace) -> None:
        """
        Setup independent Git repository for non-versioned original.
        
        Strategy: Create git in workspace storage, never touch original
        
        1. Initialize git repo in ~/.gitmats/workspaces/{id}/git/
        2. Create initial commit from symlink structure (virtual snapshot)
        3. Use git alternates pointing to COW copies for efficiency
        4. Track all COW modifications as commits
        """
        
    def create_initial_snapshot_commit(self, workspace: Workspace) -> Commit:
        """
        Create initial commit representing original state.
        
        Even though original has no Git, we create a "virtual snapshot"
        commit in our standalone repo to serve as the base for diffs.
        
        The commit tree is constructed from symlinks pointing to original.
        """
```

### 4. COW Engine

Copy-on-write implementation:

```python
class COWEngine:
    """
    Manages copy-on-write operations for files.
    
    Responsibilities:
    - Detect write operations
    - Copy files to COW layer
    - Update symlinks
    - Track modifications in metadata
    - Integrate with Git for versioning
    """
    
    def copy_up(self, workspace: Workspace, 
                rel_path: str, 
                content: bytes | None = None) -> Path:
        """
        Execute copy-on-write for a file.
        
        Steps:
        1. Copy original file to ~/.gitmats/workspaces/{id}/copies/
        2. Remove symlink in workspace
        3. Create symlink to COW copy
        4. Update metadata (mark as 'copied')
        5. Trigger git update if configured
        
        Args:
            workspace: Target workspace
            rel_path: Relative path of file
            content: Optional new content (if None, just copy)
        
        Returns:
            Path to the COW copy
        """
        
    def sync_to_git(self, workspace: Workspace, 
                    rel_path: str) -> None:
        """
        Sync COW file to Git staging area.
        
        After copy_up, optionally stage the change in Git:
        - Inherited: git add {path}
        - Standalone: git add {path} in standalone repo
        """
        
    def get_file_source(self, workspace: Workspace,
                        rel_path: str) -> FileSource:
        """
        Determine where file content comes from.
        
        Returns:
            FileSource enum:
            - ORIGINAL: symlink points to original (unchanged)
            - COW_COPY: symlink points to COW copy (modified)
            - NEW: file created in workspace (no original)
        """
```

### 5. Metadata Manager

State tracking and persistence:

```python
class MetadataManager:
    """
    Manages workspace metadata and state tracking.
    
    Uses SQLite for fast queries, Git refs for version history.
    """
    
    # Workspace Registry (global)
    schema_registry = """
        CREATE TABLE workspaces (
            workspace_id TEXT PRIMARY KEY,
            original_path TEXT NOT NULL,
            workspace_type TEXT NOT NULL,
            created_at REAL,
            last_accessed REAL,
            status TEXT DEFAULT 'active',
            git_mode TEXT  -- 'inherited' or 'standalone'
        );
        
        CREATE TABLE workspace_stats (
            workspace_id TEXT PRIMARY KEY,
            total_files INTEGER,
            copied_files INTEGER,
            new_files INTEGER,
            deleted_files INTEGER,
            disk_usage_bytes INTEGER,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
        );
    """
    
    # Per-Workspace Metadata
    schema_workspace = """
        CREATE TABLE file_state (
            relative_path TEXT PRIMARY KEY,
            state TEXT NOT NULL,  -- 'linked', 'copied', 'new', 'deleted'
            original_hash TEXT,
            original_size INTEGER,
            cow_path TEXT,
            cow_hash TEXT,
            cow_size INTEGER,
            first_modified_at REAL,
            last_modified_at REAL,
            git_tracked BOOLEAN DEFAULT TRUE
        );
        
        CREATE TABLE git_commits (
            commit_hash TEXT PRIMARY KEY,
            commit_message TEXT,
            committed_at REAL,
            files_changed_count INTEGER,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id)
        );
        
        CREATE TABLE operations_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            operation TEXT,  -- 'copy_up', 'create', 'delete', 'git_commit'
            relative_path TEXT,
            details_json TEXT
        );
    """
```

## Directory Structure

### Original Workspace (Read-Only)

```
/original/
├── .git/                          # Git repository (if exists)
│   ├── objects/                   # Object database (shared)
│   ├── refs/                      # References
│   ├── worktrees/                 # Linked worktrees
│   │   └── gitmats-{id}/          # GitMats worktree entries
│   │       ├── gitdir             # Points to workspace git
│   │       ├── HEAD               # Workspace HEAD
│   │       ├── index              # Workspace staging
│   │       └── commondir          # Shared common dir
│   └── config                     # Shared config
├── src/
│   ├── main.py                    # Symlinked to virtual
│   └── utils.py
├── images/
│   └── logo.png
└── config.yaml
```

### Virtual Workspace Storage

```
~/.gitmats/
├── registry.db                    # Global registry
├── config.yaml                    # GitMats configuration
├── templates/
│   └── workspace/                 # Template for new workspaces
│       └── .gitmats.yaml
└
└── workspaces/
    ├── user123/
    │   ├── workspace/             # Virtual working directory
    │   │   ├── src/
    │   │   │   ├── main.py        # -> symlink to original OR cow copy
    │   │   │   └── utils.py
    │   │   ├── images/
    │   │   │   └── logo.png       # -> symlink to original
    │   │   ├── config.yaml        # -> symlink to cow copy (modified)
    │   │   └── .git               # -> ../git (inherited) or ../git (standalone)
    │   │
    │   ├── git/                   # Git metadata for this workspace
    │   │   ├── HEAD               # Current branch/commit
    │   │   ├── index              # Staging area
    │   │   ├── config.worktree    # Per-worktree config
    │   │   ├── objects/           # COW objects (standalone only)
    │   │   │   └── pack/
    │   │   ├── refs/
    │   │   │   └── gitmats/
    │   │   │       ├── user123/
    │   │   │       │   ├── base       # Original HEAD at creation
    │   │   │       │   ├── cow-base   # Last sync point
    │   │   │       │   └── head       # Current state
    │   │   │       └── heads/
    │   │   │           └── main       # Workspace branch
    │   │   └── alternates          # Link to original objects (inherited)
    │   │
    │   ├── copies/                # COW file copies
    │   │   ├── src/
    │   │   │   └── main.py        # Modified copy
    │   │   └── config.yaml        # Modified copy
    │   │
    │   ├── metadata.db            # Workspace-specific metadata
    │   └── .gitmats.yaml          # Workspace config
    │
    └── user456/
        └── ...                    # Same structure
```

## File Resolution Logic

When accessing a file in virtual workspace:

```python
def resolve_file_path(workspace: Workspace, rel_path: str) -> Path:
    """
    Resolve actual file path for a virtual workspace file.
    
    Resolution order:
    1. Check metadata for file state
    2. If 'copied' or 'new': return COW copy path
    3. If 'linked': return original path
    4. If 'deleted': raise FileNotFoundError
    """
    
    state = metadata.get_file_state(workspace.id, rel_path)
    
    if state.status == 'copied':
        return workspace.cow_dir / rel_path
    elif state.status == 'new':
        return workspace.cow_dir / rel_path
    elif state.status == 'linked':
        return workspace.original / rel_path
    elif state.status == 'deleted':
        raise FileNotFoundError(f"File deleted in workspace: {rel_path}")
    
    # Default: linked to original
    return workspace.original / rel_path
```

## Integration Points

### Git Hooks Integration

```python
class GitHooksManager:
    """
    Integrate COW engine with Git hooks.
    
    Hooks installed in workspace git:
    - pre-commit: Trigger COW for unstaged changes
    - post-commit: Update metadata
    - post-checkout: Sync symlinks if needed
    """
    
    def install_hooks(self, workspace: Workspace) -> None:
        hooks_dir = workspace.git_dir / 'hooks'
        
        # pre-commit: Ensure COW for all modified files
        self.write_hook(hooks_dir / 'pre-commit', """
#!/bin/sh
# GitMats pre-commit hook
# Trigger COW for any files being committed
gmt internal sync-cow --pre-commit
""")
        
        # post-commit: Update metadata
        self.write_hook(hooks_dir / 'post-commit', """
#!/bin/sh
# GitMats post-commit hook
gmt internal update-metadata --commit
""")
```

### External Tool Integration

For IDEs and editors, provide transparent access:

```python
class VFSLayer:
    """
    VFS abstraction for external tools.
    
    Provides standard file operations that automatically
    trigger COW when needed.
    """
    
    def open(self, path: str, mode: str) -> File:
        """
        Open file with automatic COW.
        
        If mode includes 'w', 'a', or 'x':
        - Check if file is still linked
        - If linked, trigger copy_up first
        - Return file handle to COW copy
        """
        
    def save(self, path: str, content: bytes) -> None:
        """
        Save content to file with COW.
        
        Equivalent to:
        1. copy_up(path)
        2. write(content)
        3. (optional) git add
        """
```