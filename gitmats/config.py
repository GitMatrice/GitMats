"""
Configuration management for GitMats.

Handles loading and validation of GitMats configuration.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class LocalGitConfig:
    """Local Git backend configuration."""
    
    shared_objects: bool = True
    worktree_strategy: str = "linked"


@dataclass
class LakeBaseConfig:
    """LakeBase backend configuration."""
    
    api_url: Optional[str] = None
    database_id: Optional[str] = None
    api_token: Optional[str] = None  # Can be from env var
    branch_prefix: str = "gitmats-"
    parent_branch: str = "main"
    start_compute_on_create: bool = False
    auto_suspend_timeout: str = "5m"


@dataclass
class NullBackendConfig:
    """Null backend configuration."""
    
    track_metadata: bool = True


@dataclass
class VersioningConfig:
    """Versioning backend configuration."""
    
    backend: str = "local"  # "local", "lakebase", "none"
    local: LocalGitConfig = field(default_factory=LocalGitConfig)
    lakebase: LakeBaseConfig = field(default_factory=LakeBaseConfig)
    none: NullBackendConfig = field(default_factory=NullBackendConfig)


@dataclass
class GitMatsConfig:
    """Global GitMats configuration."""
    
    # Versioning
    versioning: VersioningConfig = field(default_factory=VersioningConfig)
    
    # Storage
    default_workspace_dir: str = "~/.gitmats/workspaces"
    registry_db: str = "~/.gitmats/registry.db"
    
    # Defaults
    default_git_mode: str = "inherited"
    default_hooks_enabled: bool = True
    
    def get_storage_path(self) -> Path:
        """Get expanded storage path."""
        return Path(self.default_workspace_dir).expanduser()
    
    def get_registry_db_path(self) -> Path:
        """Get expanded registry database path."""
        return Path(self.registry_db).expanduser()
    
    def get_lakebase_api_token(self) -> Optional[str]:
        """Get LakeBase API token from config or environment."""
        if self.versioning.lakebase.api_token:
            return self.versioning.lakebase.api_token
        return os.environ.get("LAKEBASE_API_TOKEN")
    
    @classmethod
    def from_yaml(cls, path: Path) -> "GitMatsConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        
        return cls._parse_config(data)
    
    @classmethod
    def _parse_config(cls, data: dict) -> "GitMatsConfig":
        """Parse configuration dictionary."""
        versioning_data = data.get("versioning", {})
        
        # Parse versioning config
        versioning = VersioningConfig(
            backend=versioning_data.get("backend", "local"),
        )
        
        # Parse local config
        if "local" in versioning_data:
            versioning.local = LocalGitConfig(**versioning_data["local"])
        
        # Parse lakebase config
        if "lakebase" in versioning_data:
            lb_data = versioning_data["lakebase"]
            versioning.lakebase = LakeBaseConfig(
                api_url=lb_data.get("api_url"),
                database_id=lb_data.get("database_id"),
                api_token=lb_data.get("api_token"),
                branch_prefix=lb_data.get("branch_prefix", "gitmats-"),
                parent_branch=lb_data.get("parent_branch", "main"),
                start_compute_on_create=lb_data.get("start_compute_on_create", False),
                auto_suspend_timeout=lb_data.get("auto_suspend_timeout", "5m"),
            )
        
        # Parse none config
        if "none" in versioning_data:
            versioning.none = NullBackendConfig(**versioning_data["none"])
        
        return cls(
            versioning=versioning,
            default_workspace_dir=data.get("default_workspace_dir", "~/.gitmats/workspaces"),
            registry_db=data.get("registry_db", "~/.gitmats/registry.db"),
            default_git_mode=data.get("default_git_mode", "inherited"),
            default_hooks_enabled=data.get("default_hooks_enabled", True),
        )
    
    def to_yaml(self, path: Path) -> None:
        """Save configuration to YAML file."""
        data = {
            "versioning": {
                "backend": self.versioning.backend,
                "local": {
                    "shared_objects": self.versioning.local.shared_objects,
                    "worktree_strategy": self.versioning.local.worktree_strategy,
                },
                "lakebase": {
                    "api_url": self.versioning.lakebase.api_url,
                    "database_id": self.versioning.lakebase.database_id,
                    "branch_prefix": self.versioning.lakebase.branch_prefix,
                    "parent_branch": self.versioning.lakebase.parent_branch,
                    "start_compute_on_create": self.versioning.lakebase.start_compute_on_create,
                    "auto_suspend_timeout": self.versioning.lakebase.auto_suspend_timeout,
                },
                "none": {
                    "track_metadata": self.versioning.none.track_metadata,
                },
            },
            "default_workspace_dir": self.default_workspace_dir,
            "registry_db": self.registry_db,
            "default_git_mode": self.default_git_mode,
            "default_hooks_enabled": self.default_hooks_enabled,
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)


def load_config(config_path: Optional[Path] = None) -> GitMatsConfig:
    """
    Load GitMats configuration.
    
    Args:
        config_path: Optional explicit config path. If None, uses default.
    
    Returns:
        GitMatsConfig instance.
    """
    if config_path:
        return GitMatsConfig.from_yaml(config_path)
    
    # Default config locations
    default_path = Path.home() / ".gitmats" / "config.yaml"
    
    if default_path.exists():
        return GitMatsConfig.from_yaml(default_path)
    
    return GitMatsConfig()