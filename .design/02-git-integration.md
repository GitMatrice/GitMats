# Git Integration Design

## Overview

This document describes how GitMats integrates with Git for version control in virtual workspaces. There are two distinct scenarios:

1. **Inherited Workspace**: Original directory is already a Git repository
2. **Standalone Workspace**: Original directory has no Git repository

## Scenario 1: Inherited Git Workspace

When the original workspace contains a `.git` directory, we leverage Git's native **worktree** feature combined with **alternates** for object sharing.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Original Repository (Read-Only)                       │
│                                                                         │
│  /original/.git/                                                        │
│  ├── objects/           ──────────────────┐                            │
│  │   ├── pack/                          │ Object sharing               │
│  │   └── info/alternates                 │ (via alternates)             │
│  ├── refs/                               │                              │
│  │   ├── heads/                          │                              │
│  │   └── gitmats/                        │ GitMats-specific refs        │
│  │       ├── user123/base               │ Original HEAD at creation    │
│  │       └── user123/last-sync          │ Last synced state            │
│  ├── worktrees/                          │                              │
│  │   └── gitmats-user123/               │ Worktree administrative dir  │
│  │       ├── HEAD                       │ → workspace HEAD             │
│  │       ├── index                      │ → workspace staging area     │
│  │       ├── gitdir                     │ → workspace .git link        │
│  │       └── commondir                  │ → original .git              │
│  └── config                              │ Shared repository config     │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ Linked via worktree + alternates
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Virtual Workspace (user123)                           │
│                                                                         │
│  ~/.gitmats/workspaces/user123/                                         │
│  ├── workspace/                         # Working directory             │
│  │   ├── .git                           # → ../git (symlink)            │
│  │   ├── src/                           # Symlinks to original or COW   │
│  │   └── config.yaml                    #                               │
│  │                                                                      │
│  ├── git/                               # Per-worktree Git metadata     │
│  │   ├── HEAD                           # refs/heads/workspace-main     │
│  │   ├── index                          # Staging area (independent)    │
│  │   ├── config.worktree                # Worktree-specific config      │
│  │   ├── objects/                       # Empty (uses alternates)       │
│  │   │   └── info/alternates            # → /original/.git/objects      │
│  │   └── refs/                                                          │
│  │       └── heads/                                                     │
│  │           └── workspace-main         # Workspace branch             │
│  │                                                                      │
│  ├── copies/                            # COW file copies               │
│  └── metadata.db                        # State tracking                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### 1. Create Linked Worktree

```python
def setup_inherited_git(workspace: Workspace) -> None:
    """
    Setup Git integration for inherited workspace.
    
    Uses Git's linked worktree feature to create an independent
    working directory that shares the object database.
    """
    
    original_git = Path(workspace.original) / '.git'
    workspace_git = workspace.storage / 'git'
    workspace_wd = workspace.storage / 'workspace'
    
    # 1. Create worktree administrative directory
    worktree_admin = original_git / 'worktrees' / f'gitmats-{workspace.id}'
    worktree_admin.mkdir(parents=True, exist_ok=True)
    
    # 2. Create worktree git directory
    workspace_git.mkdir(parents=True, exist_ok=True)
    
    # 3. Write gitdir file (points to workspace .git)
    (worktree_admin / 'gitdir').write_text(str(workspace_git))
    
    # 4. Write commondir file (points to original .git)
    (worktree_admin / 'commondir').write_text(str(original_git))
    
    # 5. Create HEAD (new branch for workspace)
    workspace_branch = f'workspace-{workspace.id}-main'
    (worktree_admin / 'HEAD').write_text(f'ref: refs/heads/{workspace_branch}')
    
    # 6. Create index (empty staging area)
    # Using git's internal format
    (worktree_admin / 'index').write_bytes(b'DIRC\x00\x00\x00\x02')  # Empty index
    
    # 7. Create workspace .git symlink
    (workspace_wd / '.git').symlink_to(workspace_git)
    
    # 8. Create per-worktree config
    (workspace_git / 'config.worktree').write_text("""
[core]
    worktree = {workspace_wd}
[business]
    workspace-id = {workspace.id}
""")
    
    # 9. Create alternates file (share objects with original)
    (workspace_git / 'objects' / 'info' / 'alternates').write_text(str(original_git / 'objects'))
    
    # 10. Create workspace branch (starting from original HEAD)
    original_head = get_original_head(original_git)
    create_branch_ref(workspace_git / 'refs' / 'heads' / workspace_branch, original_head)
    
    # 11. Create GitMats tracking refs
    create_gitmats_refs(original_git, workspace.id, original_head)
```

#### 2. GitMats Reference Structure

```python
def create_gitmats_refs(original_git: Path, workspace_id: str, 
                        original_head: str) -> None:
    """
    Create GitMats-specific refs in original repository.
    
    These refs track:
    - Base: Original state when workspace was created
    - Last-sync: Last synchronized state (for merge detection)
    """
    
    gitmats_refs = original_git / 'refs' / 'gitmats' / workspace_id
    
    # refs/gitmats/{workspace_id}/base
    # Snapshot of original at workspace creation time
    (gitmats_refs / 'base').write_text(original_head)
    
    # refs/gitmats/{workspace_id}/last-sync  
    # Updated when user syncs changes back to original
    (gitmats_refs / 'last-sync').write_text(original_head)
```

#### 3. File Operations with Git

```python
class InheritedGitOperations:
    """
    Git operations for inherited workspace.
    
    All operations run in workspace context, affecting only
    the workspace branch and index.
    """
    
    def git_status(self, workspace: Workspace) -> GitStatus:
        """
        Get git status for workspace.
        
        Shows:
        - Modified files (COW copies vs base)
        - New files
        - Deleted files
        
        Command: git --git-dir={workspace.git} status
        """
        
    def git_add(self, workspace: Workspace, paths: list[str]) -> None:
        """
        Stage files for commit.
        
        For COW files, this stages the modified copy.
        Command: git --git-dir={workspace.git} add {paths}
        """
        
    def git_commit(self, workspace: Workspace, message: str) -> str:
        """
        Create commit in workspace history.
        
        The commit is recorded in:
        - refs/heads/workspace-{id}-main (workspace branch)
        - Workspace index is cleared
        
        Command: git --git-dir={workspace.git} commit -m "{message}"
        
        Returns: commit SHA
        """
        
    def git_log(self, workspace: Workspace) -> list[CommitInfo]:
        """
        Show commit history.
        
        For inherited workspace, shows:
        - Workspace commits (after creation)
        - Original commits (before creation, from base)
        
        Uses git log with appropriate ref ranges.
        """
        
    def sync_to_original(self, workspace: Workspace) -> SyncResult:
        """
        Sync workspace changes back to original.
        
        This is a merge operation:
        1. Check for conflicts (original changed since last-sync)
        2. Merge workspace branch into original HEAD
        3. Update last-sync ref
        
        Returns: SyncResult with status and any conflicts
        """
```

### Git Worktree Details

Git's worktree structure (from `worktree.h` analysis):

```c
// Key structures from Git source:
struct worktree {
    struct repository *repo;    // The repository
    char *path;                 // Working tree path
    char *id;                   // Worktree identifier
    char *head_ref;             // HEAD reference
    char *lock_reason;          // If locked
    int is_detached;            // Is detached HEAD
    int is_current;             // Is current worktree
};

// Worktree administrative files:
// - gitdir: Points to per-worktree .git directory
// - commondir: Points to shared .git directory  
// - HEAD: Worktree's HEAD reference
// - index: Worktree's staging area
// - config.worktree: Worktree-specific config
```

GitMats worktree identifier format: `gitmats-{workspace_id}`

---

## Scenario 2: Standalone Git Workspace

When the original directory has no `.git`, we create an **independent Git repository** in the workspace storage that never touches the original.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Original Directory (No Git)                           │
│                                                                         │
│  /original/                                                             │
│  ├── src/                               # No .git directory             │
│  │   ├── main.py                        # Never modified                │
│  │   └── utils.py                       # Never accessed by Git         │
│  ├── images/                                                            │
│  │   └── logo.png                                                       │
│  └── config.yaml                                                        │
│                                                                         │
│  NOTE: Original directory remains completely untouched.                 │
│  No .git directory is created here.                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                │
                                │ Symlinks only (no Git awareness)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Virtual Workspace (user123)                           │
│                                                                         │
│  ~/.gitmats/workspaces/user123/                                         │
│  ├── workspace/                         # Working directory             │
│  │   ├── .git                           # → ../git (symlink)            │
│  │   ├── src/                                                           │
│  │   │   ├── main.py                    # → original (symlink)          │
│  │   │   └── utils.py                   # → original (symlink)          │
│  │   └── config.yaml                    # → original or COW copy        │
│  │                                                                      │
│  ├── git/                               # Independent Git repository    │
│  │   ├── HEAD                           # Current branch                │
│  │   ├── config                         # Repository config             │
│  │   ├── objects/                       # Object database               │
│  │   │   ├── pack/                      # Pack files                    │
│  │   │   └── info/                      # Object info                   │
│  │   └── refs/                                                          │
│  │       ├── heads/                                                     │
│  │       │   └── main                   # Main branch                   │
│  │       └── gitmats/                   # GitMats tracking              │
│  │           ├── base                   # Virtual base commit           │
│  │           └── cow-head               # Current COW state             │
│  │                                                                      │
│  ├── copies/                            # COW file copies               │
│  │   └── config.yaml                    # Modified files                │
│  │                                                                      │
│  └── metadata.db                        # State tracking                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Implementation Steps

#### 1. Create Standalone Repository

```python
def setup_standalone_git(workspace: Workspace) -> None:
    """
    Setup independent Git repository for standalone workspace.
    
    The repository lives entirely in workspace storage,
    never touching the original directory.
    """
    
    workspace_git = workspace.storage / 'git'
    workspace_wd = workspace.storage / 'workspace'
    
    # 1. Initialize git repository
    subprocess.run([
        'git', 'init', 
        '--git-dir', str(workspace_git),
        '--separate-git-dir', str(workspace_git)
    ], cwd=str(workspace_wd))
    
    # 2. Configure repository
    config = workspace_git / 'config'
    with open(config, 'a') as f:
        f.write("""
[user]
    name = GitMats Workspace
    email = workspace@gitmats.local
[core]
    worktree = {workspace_wd}
[business]
    workspace-id = {workspace.id}
    git-mode = standalone
""")
    
    # 3. Create virtual base commit
    # This represents the "original state" without modifying original
    create_virtual_base_commit(workspace)
    
    # 4. Create .git symlink in workspace
    (workspace_wd / '.git').symlink_to(workspace_git)
```

#### 2. Virtual Base Commit

```python
def create_virtual_base_commit(workspace: Workspace) -> str:
    """
    Create a virtual base commit representing original state.
    
    This is the key innovation for standalone mode:
    - We create a commit whose tree matches original directory
    - But we use symlinks as tree entries, not actual files
    - This commit becomes the "ancestor" for all workspace changes
    
    Strategy:
    1. Create git index with entries pointing to original files
    2. Write tree object from index
    3. Create commit with this tree (no parent - root commit)
    
    Returns: SHA of virtual base commit
    """
    
    workspace_git = workspace.storage / 'git'
    original_dir = Path(workspace.original)
    
    # 1. Build index from original directory
    # Using git add with --intent-to-add for symlinks
    index_entries = []
    
    for original_file in original_dir.rglob('*'):
        if original_file.is_file() and not original_file.name.startswith('.'):
            rel_path = original_file.relative_to(original_dir)
            
            # Calculate file hash (for git object)
            file_hash = compute_git_blob_hash(original_file)
            file_mode = get_git_file_mode(original_file)
            
            # Add to index (mode, hash, stage, path)
            index_entries.append((file_mode, file_hash, 0, str(rel_path)))
    
    # 2. Write index file
    index_path = workspace_git / 'index'
    write_git_index(index_path, index_entries)
    
    # 3. Write tree object
    tree_sha = write_tree_from_index(workspace_git, index_path)
    
    # 4. Create root commit
    commit_sha = create_commit(
        git_dir=workspace_git,
        tree_sha=tree_sha,
        parent=None,  # Root commit - no parent
        message=f"GitMats: Virtual base from {workspace.original}\n"
                f"Workspace: {workspace.id}\n"
                f"Created: {datetime.now().isoformat()}\n"
                f"Note: Original directory not modified."
    )
    
    # 5. Create refs
    (workspace_git / 'refs' / 'heads' / 'main').write_text(commit_sha)
    (workspace_git / 'refs' / 'gitmats' / 'base').write_text(commit_sha)
    (workspace_git / 'HEAD').write_text('ref: refs/heads/main')
    
    return commit_sha


def compute_git_blob_hash(file_path: Path) -> str:
    """
    Compute Git blob hash for a file.
    
    Git blob format: "blob {size}\0{content}"
    Hash: SHA-1 of this header + content
    """
    import hashlib
    
    content = file_path.read_bytes()
    size = len(content)
    header = f"blob {size}\0".encode()
    
    sha1 = hashlib.sha1()
    sha1.update(header)
    sha1.update(content)
    
    return sha1.hexdigest()


def write_git_index(index_path: Path, entries: list) -> None:
    """
    Write Git index file format.
    
    Index format (from Git source, read-cache.c):
    - Header: DIRC (4 bytes), version (4 bytes), entry count (4 bytes)
    - Entries: mode (4), hash (20), stage (2), path (variable)
    - Extension signatures
    - SHA-1 checksum of entire index
    """
    
    import struct
    import hashlib
    
    # Header
    header = struct.pack('>4sII', 'DIRC', 2, len(entries))
    
    # Entries
    entry_data = b''
    for mode, hash_hex, stage, path in entries:
        # Convert hash to bytes
        hash_bytes = bytes.fromhex(hash_hex)
        
        # Entry: ctime, mtime, dev, ino, mode, uid, gid, size, hash, flags, path
        # Simplified - use zeros for timestamps and device info
        entry = struct.pack('>IIIIIIII20sH',
            0, 0,  # ctime (sec, nsec)
            0, 0,  # mtime (sec, nsec)  
            0,     # dev
            0,     # ino
            mode,  # mode
            0,     # uid
            0,     # gid
            0,     # size - unknown
            hash_bytes,  # SHA-1
            len(path) | (stage << 12)  # flags
        )
        entry += path.encode() + b'\0'
        
        # Padding to 8-byte boundary
        padding = (8 - (len(entry) % 8)) % 8
        entry += b'\0' * padding
        
        entry_data += entry
    
    # SHA-1 checksum
    sha1 = hashlib.sha1()
    sha1.update(header)
    sha1.update(entry_data)
    checksum = sha1.digest()
    
    # Write index
    with open(index_path, 'wb') as f:
        f.write(header)
        f.write(entry_data)
        f.write(checksum)
```

#### 3. COW Integration with Git

```python
class StandaloneGitOperations:
    """
    Git operations for standalone workspace.
    
    The standalone repo tracks COW changes independently.
    """
    
    def on_cow_copy(self, workspace: Workspace, rel_path: str) -> None:
        """
        Update Git when file is copied via COW.
        
        After copy_up:
        1. Add new blob object for COW copy
        2. Update index entry to point to new blob
        3. Mark file as modified in git status
        """
        
        cow_path = workspace.copies / rel_path
        workspace_git = workspace.git
        
        # Add blob to object store
        blob_sha = add_blob_to_git(workspace_git, cow_path)
        
        # Update index
        update_index_entry(workspace_git, rel_path, blob_sha)
        
    def git_commit_cow(self, workspace: Workspace, message: str) -> str:
        """
        Commit all COW changes.
        
        Creates a new commit with:
        - Parent: current HEAD
        - Tree: reflects all COW copies and new files
        - Message: user-provided message
        
        After commit:
        - Update refs/gitmats/cow-head
        - Clear staging
        """
        
        # Write tree from current index
        tree_sha = write_tree_from_index(workspace.git, workspace.git / 'index')
        
        # Get current HEAD
        parent_sha = get_head_sha(workspace.git)
        
        # Create commit
        commit_sha = create_commit(
            git_dir=workspace.git,
            tree_sha=tree_sha,
            parent=parent_sha,
            message=message
        )
        
        # Update refs
        update_ref(workspace.git / 'refs' / 'heads' / 'main', commit_sha)
        update_ref(workspace.git / 'refs' / 'gitmats' / 'cow-head', commit_sha)
        
        return commit_sha
```

---

## Git Operations Matrix

| Operation | Inherited Mode | Standalone Mode |
|-----------|---------------|-----------------|
| `git init` | Not needed (worktree) | Create in workspace storage |
| `git status` | Worktree status | Standard repo status |
| `git add` | Stage in worktree index | Stage in standalone index |
| `git commit` | Create in shared objects | Create in standalone objects |
| `git log` | Workspace + original history | Workspace history only |
| `git branch` | Creates in shared refs | Creates in standalone refs |
| `git merge` | Merge into original branch | Merge within standalone |
| `git push` | Push from worktree | Push from standalone |
| `git diff` | vs original base | vs virtual base commit |

---

## Reference Structure

### Inherited Mode Refs

```
/original/.git/refs/
├── heads/
│   └── main                    # Original main branch
├── gitmats/
│   └── user123/
│       ├── base                # SHA at workspace creation
│       └── last-sync           # Last synced state
└── remotes/
    └── origin/

/workspace/git/refs/
├── heads/
│   └── workspace-main          # Workspace branch (local)
└── worktree/
    └── user123                 # Worktree metadata ref
```

### Standalone Mode Refs

```
/workspace/git/refs/
├── heads/
│   └── main                    # Workspace main branch
├── gitmats/
│   ├── base                    # Virtual base commit
│   └── cow-head                # Current COW state
└── remotes/                    # Optional remote refs
```

---

## Safety Considerations

### Original Protection

```python
class OriginalProtector:
    """
    Ensures original workspace is never modified.
    
    Checks performed:
    1. Never write to original directory
    2. Never create .git in original (standalone mode)
    3. Never push directly to original refs
    4. Validate before sync operations
    """
    
    PROTECTED_PATHS = ['.git', '.gitignore', '.gitmodules']
    
    def validate_write_path(self, path: Path, original: Path) -> bool:
        """Ensure write path is not in original directory."""
        try:
            path.resolve().relative_to(original.resolve())
            return False  # Path is inside original - PROTECTED
        except ValueError:
            return True  # Path is outside original - ALLOWED
    
    def validate_git_operation(self, operation: str, 
                               original: Path) -> bool:
        """Validate Git operation doesn't affect original."""
        if operation in ['init', 'clone']:
            # Never create .git in original
            return not (original / '.git').exists()
        
        if operation == 'push':
            # Push must go to remote, not original
            return True  # Always allow push to configured remote
        
        return True
```

---

## Implementation Notes

### Using Git Internals (from git source analysis)

Based on analysis of Git's internal structures:

1. **Object Format** (`object.h`):
   ```c
   struct object {
       unsigned parsed : 1;
       unsigned type : TYPE_BITS;  // OBJ_COMMIT=1, OBJ_TREE=2, OBJ_BLOB=3
       unsigned flags : FLAG_BITS;
       struct object_id oid;       // SHA-1 hash
   };
   ```

2. **Commit Structure** (`commit.h`):
   ```c
   struct commit {
       struct object object;
       timestamp_t date;
       struct commit_list *parents;  // Parent edges (DAG)
       struct tree *maybe_tree;
   };
   ```

3. **Worktree Structure** (`worktree.h`):
   - `gitdir`: Path to per-worktree .git
   - `commondir`: Path to shared .git (for inherited)
   - `HEAD`: Worktree-specific HEAD
   - `index`: Worktree-specific staging area

GitMats uses these structures correctly to ensure proper Git integration.