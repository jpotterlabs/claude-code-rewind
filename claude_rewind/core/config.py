"""Configuration management for Claude Rewind Tool."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from .interfaces import IConfigManager


@dataclass
class StorageConfig:
    """Storage-related configuration."""
    max_snapshots: int = 100
    compression_enabled: bool = True
    cleanup_after_days: int = 30
    max_disk_usage_mb: int = 1000
    compression_level: int = 3


@dataclass
class DisplayConfig:
    """Display and UI configuration."""
    theme: str = "dark"
    diff_algorithm: str = "unified"
    show_line_numbers: bool = True
    context_lines: int = 3
    syntax_highlighting: bool = True
    progress_indicators: bool = True


@dataclass
class HooksConfig:
    """Hooks and integration configuration."""
    pre_snapshot_script: Optional[str] = None
    post_rollback_script: Optional[str] = None
    claude_integration_enabled: bool = True
    auto_snapshot_enabled: bool = True


@dataclass
class GitIntegrationConfig:
    """Git integration configuration."""
    respect_gitignore: bool = True
    auto_commit_rollbacks: bool = False
    include_git_metadata: bool = True
    track_git_changes: bool = True


@dataclass
class PerformanceConfig:
    """Performance-related configuration."""
    max_file_size_mb: int = 100
    parallel_processing: bool = True
    memory_limit_mb: int = 500
    snapshot_timeout_seconds: int = 30


@dataclass
class RewindConfig:
    """Complete configuration for Claude Rewind Tool."""
    storage: StorageConfig
    display: DisplayConfig
    hooks: HooksConfig
    git_integration: GitIntegrationConfig
    performance: PerformanceConfig
    
    def __init__(self):
        self.storage = StorageConfig()
        self.display = DisplayConfig()
        self.hooks = HooksConfig()
        self.git_integration = GitIntegrationConfig()
        self.performance = PerformanceConfig()


class ConfigManager(IConfigManager):
    """Manages configuration loading, saving, and validation."""
    
    DEFAULT_CONFIG_NAME = "config.yml"
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.config_dir = self.project_root / ".claude-rewind"
        self.config_path = self.config_dir / self.DEFAULT_CONFIG_NAME
    
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        path = config_path or self.config_path
        
        if not path.exists():
            return self.get_default_config()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            
            # Merge with defaults to ensure all keys are present
            default_config = self.get_default_config()
            merged_config = self._merge_configs(default_config, config_data)
            
            return merged_config
        except Exception as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            return self.get_default_config()
    
    def save_config(self, config: Dict[str, Any], config_path: Optional[Path] = None) -> bool:
        """Save configuration to YAML file."""
        path = config_path or self.config_path
        
        try:
            # Ensure config directory exists
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Error: Failed to save config to {path}: {e}")
            return False
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        default_config = RewindConfig()
        return {
            'storage': asdict(default_config.storage),
            'display': asdict(default_config.display),
            'hooks': asdict(default_config.hooks),
            'git_integration': asdict(default_config.git_integration),
            'performance': asdict(default_config.performance)
        }
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration and return any errors."""
        errors = []
        
        # Validate storage config
        storage = config.get('storage', {})
        if storage.get('max_snapshots', 0) <= 0:
            errors.append("storage.max_snapshots must be greater than 0")
        
        if storage.get('max_disk_usage_mb', 0) <= 0:
            errors.append("storage.max_disk_usage_mb must be greater than 0")
        
        if storage.get('cleanup_after_days', 0) <= 0:
            errors.append("storage.cleanup_after_days must be greater than 0")
        
        compression_level = storage.get('compression_level', 3)
        if not (1 <= compression_level <= 22):
            errors.append("storage.compression_level must be between 1 and 22")
        
        # Validate display config
        display = config.get('display', {})
        theme = display.get('theme', 'dark')
        if theme not in ['dark', 'light', 'auto']:
            errors.append("display.theme must be 'dark', 'light', or 'auto'")
        
        diff_algorithm = display.get('diff_algorithm', 'unified')
        if diff_algorithm not in ['unified', 'side-by-side', 'context']:
            errors.append("display.diff_algorithm must be 'unified', 'side-by-side', or 'context'")
        
        context_lines = display.get('context_lines', 3)
        if context_lines < 0:
            errors.append("display.context_lines must be non-negative")
        
        # Validate performance config
        performance = config.get('performance', {})
        if performance.get('max_file_size_mb', 0) <= 0:
            errors.append("performance.max_file_size_mb must be greater than 0")
        
        if performance.get('memory_limit_mb', 0) <= 0:
            errors.append("performance.memory_limit_mb must be greater than 0")
        
        if performance.get('snapshot_timeout_seconds', 0) <= 0:
            errors.append("performance.snapshot_timeout_seconds must be greater than 0")
        
        # Validate hook scripts exist if specified
        hooks = config.get('hooks', {})
        for script_key in ['pre_snapshot_script', 'post_rollback_script']:
            script_path = hooks.get(script_key)
            if script_path and not Path(script_path).exists():
                errors.append(f"hooks.{script_key} file does not exist: {script_path}")
        
        return errors
    
    def _merge_configs(self, default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge user config with default config."""
        result = default.copy()
        
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def create_default_config_file(self) -> bool:
        """Create a default configuration file."""
        default_config = self.get_default_config()
        return self.save_config(default_config)
    
    def get_config_path(self) -> Path:
        """Get the path to the configuration file."""
        return self.config_path