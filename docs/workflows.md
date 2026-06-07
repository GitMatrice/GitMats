# GitMats Workflows

Practical examples for using GitMats in various scenarios.

---

## Workflow 1: Basic Workspace Creation

### Local Git Backend (Default)

```bash
# Configure to use local Git backend
gmt config set versioning.backend local

# Create workspace from current directory
gmt create my-feature

# Output:
# Created workspace 'my-feature'
# Type: inherited (Git versioned)
# Original: /Users/you/projects/myapp
# Location: ~/.gitmats/workspaces/my-feature/workspace
# Branch: workspace-my-feature-main
# Disk saved: 0 bytes (all files symlinked)

# Navigate to workspace
cd ~/.gitmats/workspaces/my-feature/workspace

# Make modifications - files are automatically COW'd
vim src/main.py

# Check status
gmt status my-feature
# Output:
# On branch workspace-my-feature-main
# Workspace: my-feature
#
# Changes not staged for commit:
#   modified:   src/main.py
#
# Symlinked to original (not modified):
#   45 files
#
# Disk usage: 2.5 KB (0.5% of original 500 KB)

# Commit changes
gmt commit my-feature -m "Refactor main entry point"

# View history
gmt log my-feature
# Output:
# COMMIT     MESSAGE                        TIME
# a1b2c3d    Refactor main entry point      2026-06-06 10:30
# base       Workspace creation base        2026-06-06 10:00
```

### LakeBase Backend

```bash
# Configure LakeBase backend
gmt config set versioning.backend lakebase
gmt config set versioning.lakebase.api_url https://api.dbay.cloud:8443/api/v1
gmt config set versioning.lakebase.database_id db_abc123
export LAKEBASE_API_TOKEN="your-token-here"

# Create workspace (creates LakeBase branch)
gmt create agent-exp-1 --from=/projects/myapp

# Output:
# Created workspace 'agent-exp-1'
# Type: inherited (LakeBase backend)
# Original: /Users/you/projects/myapp
# Location: ~/.gitmats/workspaces/agent-exp-1/workspace
# LakeBase branch: gitmats-agent-exp-1 (br_xyz789)
# Database: db_abc123
# Disk saved: 0 bytes (all files symlinked)

# Commit creates LakeBase version
gmt commit agent-exp-1 -m "Agent experiment: authentication refactor"

# Output:
# [lakebase] Created version ver_def456 at LSN 0/12345AB
#  Branch: gitmats-agent-exp-1
#  Files: 3 changed
#  Message: "Agent experiment: authentication refactor"

# View LakeBase version history
gmt log agent-exp-1
# Output:
# VERSION      LSN          MESSAGE                                  CREATED
# ver_def456   0/12345AB    Agent experiment: authentication refactor  2026-06-06 10:30
# ver_ghi789   0/12000CD    Initial workspace state                   2026-06-06 10:00
```

---

## Workflow 2: Agent Speculative Execution

Agents can create isolated branches to try operations, then promote or discard based on results.

### Step-by-Step Process

```bash
# 1. Agent creates speculative workspace
gmt create agent-spec-1 --from=/projects/myapp --backend=lakebase

# 2. Agent makes modifications in workspace
cd ~/.gitmats/workspaces/agent-spec-1/workspace
# Agent edits files via tool calls...

# 3. Check what changed
gmt status agent-spec-1 --files
# Output:
# FILE                STATUS      CHANGE
# src/auth.py         copied      +45 lines, -12 lines
# config.yaml         copied      +8 bytes
# src/new_module.py   new         +500 bytes

# 4. Create checkpoint version
gmt commit agent-spec-1 -m "Speculative: add OAuth support"

# 5. Agent tests the changes
python test_auth.py
# Result: PASS

# 6. If successful - promote to main
gmt promote agent-spec-1
# Output:
# Promoting workspace 'agent-spec-1' to main...
#  - Created backup branch: main-backup-20260606-1030
#  - Switched active timeline to gitmats-agent-spec-1
#  - Rebuilt compute pod
#
# Workspace promoted successfully.

# 7. If failed - destroy and discard
gmt destroy agent-spec-1 --force
# Output:
# Deleted LakeBase branch br_xyz789
# Workspace 'agent-spec-1' destroyed
# Freed 3.5 MB disk space
```

### Parallel Agent Execution

```bash
# Create multiple workspaces for parallel exploration
gmt create agent-path-a --backend=lakebase &
gmt create agent-path-b --backend=lakebase &
gmt create agent-path-c --backend=lakebase &
wait

# Each agent works in its own workspace
cd ~/.gitmats/workspaces/agent-path-a/workspace
# Agent A: Try approach A

cd ~/.gitmats/workspaces/agent-path-b/workspace
# Agent B: Try approach B

cd ~/.gitmats/workspaces/agent-path-c/workspace
# Agent C: Try approach C

# Compare results
gmt diff agent-path-a --vs-original
gmt diff agent-path-b --vs-original
gmt diff agent-path-c --vs-original

# Choose best approach and promote
gmt promote agent-path-b

# Discard others
gmt destroy agent-path-a --force
gmt destroy agent-path-c --force
```

---

## Workflow 3: CI/CD Preview Environments

### PR Preview Branch

```bash
# In CI pipeline for PR #42:

# 1. Create preview workspace from main branch
gmt create preview-pr42 --from=/repo/main --backend=lakebase

# Output:
# Created workspace 'preview-pr42'
# LakeBase branch: gitmats-preview-pr42

# 2. Apply PR changes to workspace
cd ~/.gitmats/workspaces/preview-pr42/workspace
git fetch origin pull/42/head:pr-42
git merge pr-42

# Or apply patch directly
git apply /tmp/pr-42.patch

# 3. Run tests in preview
npm test
npm run e2e-test

# 4. Create version snapshot for review
gmt commit preview-pr42 -m "PR #42 preview snapshot"

# 5. Generate preview URL
# LakeBase branch connection string:
# postgres://preview-pr42.dbay.cloud:5432/mydb?branch=gitmats-preview-pr42

# 6. Reviewers can view preview at:
# https://console.dbay.cloud/databases/db_abc123/branches/gitmats-preview-pr42

# 7. After PR merged or closed
gmt destroy preview-pr42 --force
```

### Automated Cleanup

```bash
# Scheduled cleanup for old preview workspaces
gmt prune --pattern="preview-*" --inactive=7

# Output:
# Pruning preview workspaces (> 7 days inactive)...
#
# Candidates:
#   preview-pr38    (inactive 12 days)    500 KB
#   preview-pr40    (inactive 9 days)     800 KB
#
# Removed 2 workspaces, freed 1.3 MB
```

---

## Workflow 4: Database Migration Sandbox

### Safe Migration Testing

```bash
# 1. Create sandbox workspace for migration testing
gmt create migration-test --from=/production/repo --backend=lakebase

# 2. Run migration in sandbox
cd ~/.gitmats/workspaces/migration-test/workspace

# Connect to LakeBase branch database
psql "postgres://migration-test.dbay.cloud:5432/mydb?branch=gitmats-migration-test"

# Run migration
\i migrations/2026-06-add-users-table.sql

# 3. Verify migration results
gmt diff migration-test --vs-original --schema

# Output:
# Schema diff:
#   Tables added: users, user_sessions
#   Indexes added: users_email_idx, users_pkey
#   Columns added: 12 total

# 4. Check data integrity
gmt diff migration-test --vs-original --data --table=users --limit=100

# 5. Create pre-deploy version
gmt commit migration-test -m "Migration 2026-06: users table - pre-deploy snapshot"

# 6. If validation passes, promote to production
gmt promote migration-test

# Output:
# Promoting workspace 'migration-test' to main...
#  - Created backup: main-backup-20260606-migration
#  - Migration applied to production timeline
#
# Migration complete. Users table now in production.

# 7. If issues found, restore to previous version
gmt restore migration-test --version=ver_pre-migration

# Output:
# Restored to version ver_pre-migration
# Created backup: migration-test-backup-20260606
# Migration rolled back, users table removed
```

---

## Workflow 5: Version Restoration

### Restore to Previous State

```bash
# View version history
gmt log my-project

# Output:
# VERSION      LSN          MESSAGE                        CREATED
# ver_abc123   0/15A000     Current state                  2026-06-06 15:00
# ver_def456   0/14B000     Add OAuth support              2026-06-06 12:00
# ver_ghi789   0/130000     Refactor auth module           2026-06-06 10:00
# ver_jkl012   0/12A000     Initial schema                 2026-06-05 09:00

# Restore to specific version
gmt restore my-project --version=ver_ghi789

# Output:
# Restoring workspace 'my-project' to version ver_ghi789...
#
# Checking for changes after target version...
#   Versions after ver_ghi789:
#     - ver_def456 (Add OAuth support)
#     - ver_abc123 (Current state)
#
# Creating backup branch...
#   Backup: my-project-backup-20260606-1515 (br_backup_xyz)
#   Preserves: ver_def456, ver_abc123
#
# Creating new timeline from ver_ghi789 snapshot...
#   New timeline: tl_new_abc
#   LSN: 0/130000
#
# Rebuilding workspace symlinks...
#   Reset 5 files to version state
#   Removed 3 files created after version
#
# Restore complete.
# Workspace now at "Refactor auth module" state.
```

### Post-Restore Exploration

```bash
# After restore, the backup branch preserves later versions
gmt log my-project-backup-20260606-1515

# Output:
# VERSION      MESSAGE                        CREATED
# ver_abc123   Current state (pre-restore)    2026-06-06 15:00
# ver_def456   Add OAuth support              2026-06-06 12:00

# Note: These versions are in backup branch, not current workspace

# Can create workspace from backup to explore pre-restore state
gmt create explore-pre-restore --from-branch=my-project-backup-20260606-1515

# Work in backup state
cd ~/.gitmats/workspaces/explore-pre-restore/workspace
# Examine OAuth code that was rolled back...

# Decide to bring OAuth back
gmt promote explore-pre-restore
# Or discard
gmt destroy explore-pre-restore --force
```

---

## Workflow 6: Backend Migration

### Migrate from Local Git to LakeBase

```bash
# 1. Export existing workspace history
gmt export my-feature --format=lakebase-metadata --output=/tmp/my-feature-export.json

# Output:
# Exported workspace 'my-feature'
#  Commits: 5
#  Files tracked: 45
#  Export file: /tmp/my-feature-export.json

# 2. Configure LakeBase backend
gmt config set versioning.backend lakebase
gmt config set versioning.lakebase.database_id db_abc123

# 3. Migrate workspace
gmt migrate my-feature --to-lakebase

# Output:
# Migrating workspace 'my-feature' to LakeBase backend...
#
# Creating LakeBase branch...
#   Branch: gitmats-my-feature (br_new_xyz)
#   Parent: main
#
# Importing commit history...
#   Commit 1: "Initial commit" -> version ver_import_1
#   Commit 2: "Add auth" -> version ver_import_2
#   Commit 3: "Refactor" -> version ver_import_3
#   Commit 4: "Fix bug" -> version ver_import_4
#   Commit 5: "Update docs" -> version ver_import_5
#
# Syncing file metadata...
#   Synced 45 files to gitmats_file_metadata table
#   COW copies remain on local disk
#
# Migration complete.
# Workspace 'my-feature' now uses LakeBase backend.
```

### Migrate from LakeBase to Local Git

```bash
# 1. Export LakeBase versions
gmt export my-project --from-lakebase --output=/tmp/lakebase-export.json

# Output:
# Exported workspace 'my-project' from LakeBase
#  Versions: 8
#  Branch: gitmats-my-project (br_xyz)
#  Export file: /tmp/lakebase-export.json

# 2. Switch to local backend
gmt config set versioning.backend local

# 3. Convert workspace
gmt migrate my-project --to-local

# Output:
# Migrating workspace 'my-project' to local Git backend...
#
# Creating local Git repository...
#   Git dir: ~/.gitmats/workspaces/my-project/git
#
# Importing version history as commits...
#   Version ver_001 -> commit abc123
#   Version ver_002 -> commit def456
#   ...
#   Version ver_008 -> commit xyz789
#
# Preserving file metadata...
#   gitmats_file_metadata table cleared (migrated to local)
#   COW copies preserved
#
# Migration complete.
# Workspace 'my-project' now uses local Git backend.
```

---

## Workflow 7: Data Analysis Sandbox

### Zero-Copy Data Branching

```bash
# Create sandbox for data analysis
gmt create analytics-sandbox --backend=lakebase --database=db_analytics

# Output:
# Created workspace 'analytics-sandbox'
# Type: database workspace
# LakeBase branch: gitmats-analytics-sandbox
# Connection: postgres://analytics.dbay.cloud:5432/analytics?branch=gitmats-analytics-sandbox
#
# Zero-copy branch from main timeline
# Original: 5 GB of data
# Branch overhead: 0 MB (until modifications)

# Connect to sandbox database
psql "postgres://analytics.dbay.cloud:5432/analytics?branch=gitmats-analytics-sandbox"

# Run expensive queries without affecting production
SELECT COUNT(*) FROM events WHERE timestamp > '2026-01-01';
-- Result: 10M rows scanned (only in branch)

# Create temporary indexes
CREATE INDEX temp_idx ON events(user_id);

# Run analysis queries
SELECT user_id, COUNT(*) FROM events GROUP BY user_id;

# Save analysis results as version
gmt commit analytics-sandbox -m "June 2026 user activity analysis"

# Export results
\copy (SELECT * FROM analysis_results) TO '/tmp/results.csv' CSV

# Destroy sandbox (reclaims all branch storage)
gmt destroy analytics-sandbox --force

# Output:
# Deleted LakeBase branch gitmats-analytics-sandbox
# Freed 500 MB (temp index + analysis data)
# Original production database unchanged
```

---

## Common Pitfalls

### Pitfall 1: Workspace Not Activated

```bash
# Problem: Created workspace but can't access files
gmt create my-workspace
cd ~/.gitmats/workspaces/my-workspace/workspace
ls -la
# Output: empty or error

# Solution: Workspace needs to be in working directory context
gmt status my-workspace
# If shows "inactive", activate:
gmt activate my-workspace
```

### Pitfall 2: LakeBase Compute Not Started

```bash
# Problem: Can't connect to LakeBase branch
psql "postgres://db.dbay.cloud/mydb?branch=gitmats-test"
# Error: connection refused

# Solution: Start compute explicitly
gmt compute start test-workspace

# Output:
# Starting compute for workspace 'test-workspace'...
#  Compute pod: compute-test-workspace-abc123
#  Status: running
#  Ready in: 8 seconds
#
# Connection: postgres://db.dbay.cloud:5432/mydb?branch=gitmats-test

# Alternative: Use --start-compute on create
gmt create test-workspace --backend=lakebase --start-compute
```

### Pitfall 3: Restore Creates Orphaned Versions

```bash
# Problem: After restore, versions appear "lost"
gmt restore my-project --version=ver_002
gmt log my-project
# Shows only ver_001, ver_002

# Solution: Versions moved to backup branch
gmt list --all
# Output:
# WORKSPACE              BRANCH                        STATUS
# my-project             gitmats-my-project            active
# my-project-backup      my-project-backup-20260606    backup

gmt log my-project-backup
# Shows ver_003, ver_004, ver_005 (post-restore versions)
```

### Pitfall 4: Concurrent Workspace Operations

```bash
# Problem: Two agents trying to promote same workspace
# Agent A: gmt promote workspace-1
# Agent B: gmt promote workspace-1 (concurrently)

# Error:
# Conflict: workspace 'workspace-1' locked by operation 'promote'
# Wait for lock release or use --force-lock

# Solution: Use workspace locks
gmt lock workspace-1
# Agent A does operations
gmt unlock workspace-1

# Or use explicit workspace ID per agent
gmt create agent-1-workspace --backend=lakebase
gmt create agent-2-workspace --backend=lakebase
```

### Pitfall 5: Disk Quota Exceeded

```bash
# Problem: COW copies exceed disk limit
gmt commit my-workspace -m "Large change"
# Error: Disk quota exceeded (limit: 5 GB, used: 5.2 GB)

# Solution: Check usage and reset files
gmt status my-workspace --disk-usage
# Output:
# Disk usage: 5.2 GB (104% of quota)
# Top files:
#   data/export.csv    2.1 GB
#   logs/app.log       1.5 GB

# Reset large files to original
gmt reset my-workspace data/export.csv logs/app.log

# Output:
# Reset 'data/export.csv' to original state
#  Freed 2.1 GB
# Reset 'logs/app.log' to original state
#  Freed 1.5 GB
#
# Current disk usage: 1.6 GB (32% of quota)

# Now commit succeeds
gmt commit my-workspace -m "Large change"
```

---

## Quick Reference

### Essential Commands

```bash
# Workspace management
gmt create <id> [--from=<path>] [--backend=<type>]
gmt list [--verbose]
gmt status <id> [--files]
gmt destroy <id> [--force]

# Version control
gmt commit <id> -m "message"
gmt log <id>
gmt diff <id> [--vs-original | --vs-version=<id>]
gmt restore <id> --version=<id>

# LakeBase-specific
gmt promote <id>                    # Branch becomes main
gmt compute start <id>              # Start compute pod
gmt compute stop <id>               # Suspend compute

# Configuration
gmt config set versioning.backend <type>
gmt config set versioning.lakebase.api_url <url>
gmt config set versioning.lakebase.database_id <id>
gmt config show

# Cleanup
gmt prune --inactive=<days>
gmt migrate <id> --to-lakebase | --to-local
```

### Backend Selection Guide

| Use Case | Recommended Backend | Reason |
|----------|--------------------|--------|
| Local file development | `local` | Simpler, Git-native |
| Agent speculative execution | `lakebase` | Branch isolation, promote workflow |
| CI/CD preview environments | `lakebase` | Auto cleanup, zero-copy |
| Database migration testing | `lakebase` | Schema diff, safe restore |
| Data analysis sandbox | `lakebase` | Zero-copy data branching |
| Quick throwaway experiments | `none` | No version history needed |

### File Locations

```
~/.gitmats/
├── config.yaml                    # Global configuration
├── registry.db                    # Workspace registry
└── workspaces/
    ├── <workspace-id>/
    │   ├── workspace/             # Working directory (symlinks)
    │   ├── git/                   # Git metadata (local backend)
    │   ├── copies/                # COW file copies
    │   ├── metadata.db            # File state tracking
    │   └── .gitmats.yaml          # Workspace config
    └── ...
```

### Environment Variables

```bash
# LakeBase API token (preferred over config file)
export LAKEBASE_API_TOKEN="your-token-here"

# Override default GitMats directory
export GITMATS_HOME="/custom/path"

# Proxy settings (if behind corporate firewall)
export HTTPS_PROXY="http://proxy.company.com:8080"
```