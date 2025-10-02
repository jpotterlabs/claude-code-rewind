"""Hook registration system for .claude/settings.json."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HookRegistrationError(Exception):
    """Raised when hook registration fails."""
    pass


def get_claude_settings_path(project_root: Optional[Path] = None) -> Path:
    """Get path to .claude/settings.json.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Path to .claude/settings.json
    """
    if project_root is None:
        project_root = Path.cwd()

    return project_root / ".claude" / "settings.json"


def load_claude_settings(settings_path: Path) -> Dict[str, Any]:
    """Load existing Claude settings.

    Args:
        settings_path: Path to settings.json

    Returns:
        Settings dictionary (empty if file doesn't exist)
    """
    if not settings_path.exists():
        return {}

    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse {settings_path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Failed to read {settings_path}: {e}")
        return {}


def save_claude_settings(settings_path: Path, settings: Dict[str, Any]) -> None:
    """Save Claude settings to file.

    Args:
        settings_path: Path to settings.json
        settings: Settings dictionary to save

    Raises:
        HookRegistrationError: If save fails
    """
    try:
        # Create .claude directory if it doesn't exist
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Write settings with pretty formatting
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)

        logger.info(f"Saved Claude settings to {settings_path}")

    except Exception as e:
        raise HookRegistrationError(f"Failed to save settings: {e}")


def register_native_hooks(project_root: Optional[Path] = None) -> None:
    """Register Claude Code Rewind hooks in .claude/settings.json.

    This configures Claude Code 2.0 to call claude-rewind when events fire.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Raises:
        HookRegistrationError: If registration fails
    """
    settings_path = get_claude_settings_path(project_root)

    # Load existing settings
    settings = load_claude_settings(settings_path)

    # Create hooks configuration
    hooks_config = {
        "SessionStart": {
            "command": "claude-rewind",
            "args": ["hook-handler", "session-start"],
            "background": True,
            "description": "Initialize Claude Code Rewind session tracking"
        },
        "PreToolUse": {
            "command": "claude-rewind",
            "args": ["hook-handler", "pre-tool-use"],
            "background": True,
            "description": "Capture pre-change state"
        },
        "PostToolUse": {
            "command": "claude-rewind",
            "args": ["hook-handler", "post-tool-use"],
            "background": True,
            "description": "Create automatic snapshot after tool use"
        },
        "SubagentStart": {
            "command": "claude-rewind",
            "args": ["hook-handler", "subagent-start"],
            "background": True,
            "description": "Track subagent delegation"
        },
        "SubagentStop": {
            "command": "claude-rewind",
            "args": ["hook-handler", "subagent-stop"],
            "background": True,
            "description": "Capture subagent work completion"
        },
        "Error": {
            "command": "claude-rewind",
            "args": ["hook-handler", "error"],
            "background": True,
            "description": "Auto-suggest rollback on errors"
        },
        "SessionEnd": {
            "command": "claude-rewind",
            "args": ["hook-handler", "session-end"],
            "background": True,
            "description": "Finalize session tracking"
        }
    }

    # Merge with existing hooks (preserve user's other hooks)
    if 'hooks' not in settings:
        settings['hooks'] = {}

    # Add Rewind hooks
    for hook_name, hook_config in hooks_config.items():
        settings['hooks'][hook_name] = hook_config

    # Save updated settings
    save_claude_settings(settings_path, settings)

    logger.info(f"Registered {len(hooks_config)} hooks in {settings_path}")


def unregister_hooks(project_root: Optional[Path] = None) -> None:
    """Remove Claude Code Rewind hooks from .claude/settings.json.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Raises:
        HookRegistrationError: If unregistration fails
    """
    settings_path = get_claude_settings_path(project_root)

    # Load existing settings
    settings = load_claude_settings(settings_path)

    if 'hooks' not in settings:
        logger.info("No hooks configured, nothing to remove")
        return

    # Remove Rewind hooks (ones that call claude-rewind)
    hooks = settings['hooks']
    rewind_hooks = [
        name for name, config in hooks.items()
        if isinstance(config, dict) and config.get('command') == 'claude-rewind'
    ]

    for hook_name in rewind_hooks:
        del hooks[hook_name]

    # Save updated settings
    save_claude_settings(settings_path, settings)

    logger.info(f"Removed {len(rewind_hooks)} Rewind hooks from {settings_path}")


def get_registered_hooks(project_root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Get currently registered Rewind hooks.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Dictionary of registered Rewind hooks
    """
    settings_path = get_claude_settings_path(project_root)
    settings = load_claude_settings(settings_path)

    if 'hooks' not in settings:
        return {}

    # Filter for Rewind hooks only
    hooks = settings['hooks']
    return {
        name: config for name, config in hooks.items()
        if isinstance(config, dict) and config.get('command') == 'claude-rewind'
    }


def is_hooks_registered(project_root: Optional[Path] = None) -> bool:
    """Check if native hooks are registered.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        True if hooks are registered
    """
    return len(get_registered_hooks(project_root)) > 0
