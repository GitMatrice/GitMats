# GitMats CLI Reference

`gmt` is the command-line interface for GitMats. It follows Git's CLI conventions and integrates seamlessly with existing Git workflows.

## Command Overview

```
gmt <command> [<args>]

Commands:
  Workspace Management:
    create    Create new virtual workspace
    list      List all workspaces
    status    Show workspace state
    destroy   Remove workspace
    prune     Clean up old workspaces
    lock      Lock workspace
    unlock    Unlock workspace

  Version Control:
    commit    Commit changes in workspace
    diff      Compare with original
    log       Show workspace history

  Configuration:
    config    Manage configuration
```

---

## gmt create

Create a new virtual workspace.

```bash
gmt create <workspace-id> [options]

OPTIONS:
  --from=<path>           Original workspace path (default: current directory)
  --type=<type>           Workspace type: 'inherited' or 'standalone' (default: auto-detect)
  --branch=<name>         Initial branch name (default: workspace-{id}-main)
  --lock                  Lock workspace after creation
  --quiet                 Suppress output
  --force                 Overwrite existing workspace
```

### Examples

```bash
# Create from current directory (auto-detect Git)
gmt create user123

# Create from specific original path
gmt create user456 --from=/projects/myapp

# Force standalone mode (no Git integration)
gmt create review-1 --from=/data/reports --type=standalone

# Create with custom branch
gmt create feature-x --branch=feature-auth
```

### Output

```
Created workspace 'user123'
Type: inherited (Git versioned)
Original: /projects/myapp
Location: ~/.gitmats/workspaces/user123/workspace
Branch: workspace-user123-main
Disk saved: 0 bytes (all files symlinked)

To start working:
  cd ~/.gitmats/workspaces/user123/workspace
```

---

## gmt list

List all virtual workspaces.

```bash
gmt list [options]

OPTIONS:
  --all                   Include destroyed workspaces
  --verbose               Show detailed statistics
  --porcelain             Machine-readable output
  --format=<format>       Output format: 'table', 'json', 'simple'
```

### Output (default)

```
WORKSPACE    TYPE        ORIGINAL              STATUS    DISK USAGE
user123      inherited   /projects/myapp       active    2.5 MB (5%)
user456      standalone  /data/reports         active    128 KB (1%)
review-1     inherited   /projects/myapp       locked    0 bytes
```

### Output (--verbose)

```
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

---

## gmt status

Show workspace state and modifications.

```bash
gmt status <workspace-id> [options]

OPTIONS:
  --short                 Short format (like git status --short)
  --branch                Show branch information
  --porcelain             Machine-readable output
  --files                 List all modified files
```

### Output (default)

```
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
```

### Output (--short)

```
M src/auth.py
A src/new_module.py
M config.yaml (unstaged)
```

---

## gmt commit

Commit changes in workspace.

```bash
gmt commit <workspace-id> [options]

OPTIONS:
  -m <message>            Commit message
  -a                      Stage all modified files before commit
  --amend                 Amend previous commit
  --allow-empty           Allow empty commit
  --author=<author>       Override author
```

### Examples

```bash
# Commit with message
gmt commit user123 -m "Add authentication module"

# Stage and commit all changes
gmt commit user123 -a -m "Update configuration"

# Amend previous commit
gmt commit user123 --amend -m "Updated message"
```

### Output

```
[workspace-user123-main a1b2c3d] Add authentication module
 2 files changed, 45 insertions(+), 12 deletions(-)
 create mode 100644 src/new_module.py

Workspace stats:
  Files copied: 13
  Disk usage: 2.5 MB (5%)
```

---

## gmt diff

Compare workspace with original state.

```bash
gmt diff <workspace-id> [options]

OPTIONS:
  --vs-original           Compare with original (default)
  --vs-base               Compare with workspace creation base
  --vs-commit=<sha>       Compare with specific commit
  --stat                  Show diffstat only
  --file=<path>           Diff specific file
  --color                 Color output
```

### Examples

```bash
# Diff all changes vs original
gmt diff user123

# Diff specific file
gmt diff user123 --file=src/auth.py

# Show statistics only
gmt diff user123 --stat
```

### Output

```
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

---

## gmt log

Show workspace history.

```bash
gmt log <workspace-id> [options]

OPTIONS:
  --oneline               One line per commit
  --limit=<n>             Limit number of commits
  --format=<format>       Custom format string
```

### Output

```
COMMIT     MESSAGE                        TIME
a1b2c3d    Refactor main entry point      2026-06-06 10:30
d4e5f6g    Add authentication module      2026-06-06 10:15
base       Workspace creation base        2026-06-06 10:00
```

---

## gmt destroy

Remove workspace completely.

```bash
gmt destroy <workspace-id> [options]

OPTIONS:
  --force                 Force destruction even with uncommitted changes
  --keep-backup           Keep backup of COW copies
  --archive               Archive workspace to tar.gz
  --dry-run               Show what would be destroyed
```

### Examples

```bash
# Destroy with confirmation
gmt destroy user123

# Force destroy
gmt destroy user123 --force

# Archive before destroy
gmt destroy user123 --archive --keep-backup
```

### Output

```
Destroying workspace 'user123'...

Files to remove:
  COW copies: 13 files (2.5 MB)
  Git objects: 45 objects (1.2 MB)
  Metadata: 1 database

Original workspace unchanged: /projects/myapp

Workspace 'user123' destroyed.
Freed 3.7 MB disk space.
```

---

## gmt prune

Clean up old/unused workspaces.

```bash
gmt prune [options]

OPTIONS:
  --pattern=<pattern>     Match workspace ID pattern (e.g., "preview-*")
  --inactive=<days>       Remove workspaces inactive for <days>
  --expire=<time>         Expire workspaces older than <time>
  --dry-run               Show what would be pruned
  --all                   Prune all destroyed workspaces
```

### Examples

```bash
# Prune workspaces inactive for 30 days
gmt prune --inactive=30

# Prune preview workspaces older than 7 days
gmt prune --pattern="preview-*" --inactive=7

# Preview what would be pruned
gmt prune --inactive=30 --dry-run
```

### Output

```
Pruning inactive workspaces (> 30 days)...

Candidates:
  review-old    (inactive 45 days)    500 KB
  temp-ws       (inactive 60 days)    1.2 MB

Removed 2 workspaces, freed 1.7 MB
```

---

## gmt lock / gmt unlock

Lock or unlock a workspace for exclusive access.

```bash
gmt lock <workspace-id>
gmt unlock <workspace-id>
```

Locked workspaces cannot be modified or destroyed by other processes.

---

## gmt config

Manage GitMats configuration.

```bash
gmt config set <key> <value>
gmt config get <key>
gmt config show
gmt config edit
```

### Configuration Keys

```yaml
# ~/.gitmats/config.yaml

gitmats_home: ~/.gitmats           # Base directory for all data

versioning:
  backend: local | lakebase | none # Versioning backend type
  
  lakebase:
    api_url: https://api.dbay.cloud:8443/api/v1
    database_id: db_xxx
    api_token: ${LAKEBASE_API_TOKEN}  # Use env var

storage:
  max_workspace_size: 5GB          # Maximum workspace disk quota
  auto_prune: true                 # Auto-prune destroyed workspaces
  prune_after_days: 30             # Days before auto-prune
```

### Examples

```bash
# Set backend
gmt config set versioning.backend lakebase

# Set LakeBase API URL
gmt config set versioning.lakebase.api_url https://api.example.com/v1

# Show all configuration
gmt config show

# Get specific value
gmt config get versioning.backend
```

---

## Environment Variables

```bash
# LakeBase API token (preferred over config file)
export LAKEBASE_API_TOKEN="your-token-here"

# Override default GitMats directory
export GITMATS_HOME="/custom/path"

# Disable colors in output
export NO_COLOR=1
```

---

## File Locations

```
~/.gitmats/
├── config.yaml                    # Global configuration
├── registry.db                    # Workspace registry (SQLite)
└── workspaces/
    ├── <workspace-id>/
    │   ├── workspace/             # Working directory (symlinks)
    │   ├── git/                   # Git metadata (local backend)
    │   ├── copies/                # COW file copies
    │   ├── metadata.db            # File state tracking
    │   └── .gitmats.yaml          # Workspace config
    └── ...
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Command syntax error |
| 3 | Workspace not found |
| 4 | Configuration error |
| 5 | Permission denied |
| 6 | Disk quota exceeded |