"""Hook system manager."""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Type, Optional
from importlib import import_module, util

from .base import BaseHook
from .context import HookContext

logger = logging.getLogger(__name__)

class HookManager:
    """Manages hook registration and execution."""
    
    def __init__(self, config_path: Optional[Path] = None) -> None:
        """Initialize hook manager.
        
        Args:
            config_path: Optional path to hook configuration file
        """
        self.hooks: Dict[str, List[BaseHook]] = {
            'pre_action': [],
            'post_action': []
        }
        self.config = self._load_config(config_path) if config_path else {}
        self._register_hooks()
    
    def _load_config(self, config_path: Path) -> Dict:
        """Load hook configuration from file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        try:
            return yaml.safe_load(config_path.read_text())
        except Exception as e:
            logger.error(f"Failed to load hook config from {config_path}: {e}")
            return {}
    
    def _register_hooks(self) -> None:
        """Register configured hooks."""
        for hook_config in self.config.get('hooks', []):
            try:
                hook_type = hook_config['type']
                hook_class = self._get_hook_class(hook_type)
                if hook_class:
                    hook = hook_class()
                    if error := hook.validate_config(hook_config.get('config', {})):
                        logger.error(f"Invalid config for {hook_type}: {error}")
                        continue
                    
                    hook.initialize(hook_config.get('config', {}))
                    phase = hook_config.get('phase', 'post_action')
                    if phase in self.hooks:
                        self.hooks[phase].append(hook)
                        logger.debug(f"Registered {hook_type} for phase {phase}")
            except Exception as e:
                logger.error(f"Failed to register hook {hook_config.get('type')}: {e}")
    
    def _get_hook_class(self, hook_type: str) -> Optional[Type[BaseHook]]:
        """Get hook class by type name.
        
        Args:
            hook_type: Name of hook class
            
        Returns:
            Hook class if found, None otherwise
        """
        try:
            # First check built-in hooks
            built_in_path = f".plugins.{hook_type.lower()}"
            try:
                if util.find_spec(built_in_path, package="claude_rewind.hooks"):
                    module = import_module(built_in_path, package="claude_rewind.hooks")
                    return getattr(module, hook_type)
            except ImportError:
                pass
                
            # Then check test hooks
            test_path = f"tests.hooks.plugins.test_hook"
            try:
                if util.find_spec(test_path):
                    module = import_module(test_path)
                    return getattr(module, hook_type)
            except ImportError:
                pass
            
            # Then check external plugins
            for plugin_dir in self._get_plugin_dirs():
                plugin_path = plugin_dir / f"{hook_type.lower()}.py"
                if plugin_path.exists():
                    spec = util.spec_from_file_location(
                        hook_type,
                        plugin_path
                    )
                    if spec and spec.loader:
                        module = util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        return getattr(module, hook_type)
            
            logger.error(f"Hook type not found: {hook_type}")
            return None
            
        except Exception as e:
            logger.error(f"Error loading hook class {hook_type}: {e}")
            return None
    
    def _get_plugin_dirs(self) -> List[Path]:
        """Get directories to search for plugins.
        
        Returns:
            List of plugin directory paths
        """
        dirs = [
            Path.home() / ".claude-rewind/plugins",
            Path.cwd() / ".claude-rewind/plugins",
            # Include test plugins directory when running tests
            Path(__file__).parent.parent.parent / "tests/hooks/plugins"
        ]
        return [d for d in dirs if d.exists()]
    
    def execute_pre_action(self, context: HookContext) -> bool:
        """Execute pre-action hooks.
        
        Args:
            context: Hook context
            
        Returns:
            True if execution should continue, False if cancelled
        """
        for hook in self.hooks['pre_action']:
            if not hook.enabled:
                continue
                
            try:
                hook.pre_action(context)
                if context.is_cancelled:
                    logger.info(f"Action cancelled by {hook.hook_type}")
                    return False
            except Exception as e:
                logger.error(f"Error in pre-action hook {hook.hook_type}: {e}")
                context.add_error(f"Hook error: {e}")
        
        return True
    
    def execute_post_action(self, context: HookContext) -> None:
        """Execute post-action hooks.
        
        Args:
            context: Hook context
        """
        for hook in self.hooks['post_action']:
            if not hook.enabled:
                continue
                
            try:
                hook.post_action(context)
            except Exception as e:
                logger.error(f"Error in post-action hook {hook.hook_type}: {e}")
                context.add_error(f"Hook error: {e}")
    
    def cleanup(self) -> None:
        """Clean up all hooks."""
        for hooks in self.hooks.values():
            for hook in hooks:
                try:
                    hook.cleanup()
                except Exception as e:
                    logger.error(f"Error cleaning up hook {hook.hook_type}: {e}")
    
    def disable_hook(self, hook_type: str) -> None:
        """Disable a hook by type.
        
        Args:
            hook_type: Type of hook to disable
        """
        for hooks in self.hooks.values():
            for hook in hooks:
                if hook.hook_type == hook_type:
                    hook.enabled = False
                    logger.debug(f"Disabled hook: {hook_type}")
    
    def enable_hook(self, hook_type: str) -> None:
        """Enable a hook by type.
        
        Args:
            hook_type: Type of hook to enable
        """
        for hooks in self.hooks.values():
            for hook in hooks:
                if hook.hook_type == hook_type:
                    hook.enabled = True
                    logger.debug(f"Enabled hook: {hook_type}")
    
    def __enter__(self) -> 'HookManager':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()