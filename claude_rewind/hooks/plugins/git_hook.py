"""Git integration hook."""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from ..base import BaseHook
from ..context import HookContext

logger = logging.getLogger(__name__)

class GitHook(BaseHook):
    """Hook for Git integration."""
    
    hook_type = "GitHook"
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize git hook.
        
        Args:
            config: Hook configuration
        """
        super().initialize(config)
        self.commit_message_template = config.get('commit_message', 'AI: {action_type}')
        self.auto_commit = config.get('auto_commit', True)
        self.repo = None
    
    def validate_config(self, config: Dict[str, Any]) -> Optional[str]:
        """Validate git hook configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        if 'commit_message' in config and not isinstance(config['commit_message'], str):
            return "commit_message must be a string"
        if 'auto_commit' in config and not isinstance(config['auto_commit'], bool):
            return "auto_commit must be a boolean"
        return None
    
    def _initialize_repo(self, context: HookContext) -> None:
        """Initialize git repo from context if not already done."""
        if self.repo is None:
            try:
                import git
                self.repo = git.Repo(str(context.project_root), search_parent_directories=False)
                logger.debug(f"Git repository found at {self.repo.working_dir}")
            except Exception as e:
                logger.warning(f"Failed to initialize git repository: {e}")
    
    def pre_action(self, context: HookContext) -> None:
        """Called before an action is executed.
        
        Args:
            context: Hook context
        """
        super().pre_action(context)
        
        self._initialize_repo(context)
        
        if not self.repo:
            return
            
        try:
            # Store current git status
            context.metadata['git_status'] = {
                'branch': self.repo.active_branch.name,
                'dirty': self.repo.is_dirty(),
                'untracked': [str(f) for f in self.repo.untracked_files]
            }
        except Exception as e:
            logger.warning(f"Failed to store git status: {e}")
    
    def post_action(self, context: HookContext) -> None:
        """Called after an action is executed.
        
        Args:
            context: Hook context
        """
        super().post_action(context)
        
        self._initialize_repo(context)
        
        if not self.repo or not self.auto_commit:
            return
            
        try:
            # Check if files were modified
            modified_files = [f for f in context.files if Path(f).exists()]
            if not modified_files:
                return
                
            # Stage modified files
            self.repo.index.add([str(f) for f in modified_files])
            
            # Create commit message
            msg = self.commit_message_template.format(
                action_type=context.action_type,
                files=", ".join(str(f) for f in modified_files)
            )
            
            # Commit changes
            commit = self.repo.index.commit(msg)
            logger.info(f"Created git commit {commit.hexsha[:8]}")
            
            # Store commit info in context
            context.metadata['git_commit'] = {
                'hash': commit.hexsha,
                'message': msg
            }
            
        except Exception as e:
            error = f"Failed to commit changes: {e}"
            logger.error(error)
            context.add_error(error)
    
    def cleanup(self) -> None:
        """Clean up git hook."""
        self.repo = None