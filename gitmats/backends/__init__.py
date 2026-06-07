"""
GitMats versioning backends.

Provides different versioning strategies:
- NullBackend: No versioning (ephemeral workspaces)
- LocalGitBackend: Local Git repository versioning
- LakeBaseBackend: LakeBase API versioning (Phase 7)
"""

from gitmats.backends.null import NullBackend

__all__ = ["NullBackend"]