"""Base classes for hook system."""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path

from .context import HookContext

logger = logging.getLogger(__name__)

class BaseHook(ABC):
    """Base class for all hooks."""
    
    def __init__(self) -> None:
        self.initialized = False
        self.config: Dict[str, Any] = {}
        self.enabled = True
    
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize hook with configuration.

        Args:
            config: Hook configuration
        """
        self.config = config
        self.initialized = True
        self.on_initialize(config)

    def pre_action(self, context: HookContext) -> None:
        """Called before an action is executed.

        Args:
            context: Hook context
        """
        if not self.initialized:
            raise RuntimeError(f"Hook {self.__class__.__name__} not initialized")
        self.on_pre_action(context)

    def post_action(self, context: HookContext) -> None:
        """Called after an action is executed.

        Args:
            context: Hook context
        """
        if not self.initialized:
            raise RuntimeError(f"Hook {self.__class__.__name__} not initialized")
        self.on_post_action(context)

    @abstractmethod
    def on_initialize(self, config: Dict[str, Any]) -> None:
        """Hook-specific initialization logic. Override in subclasses.

        Args:
            config: Hook configuration
        """
        ...

    @abstractmethod
    def on_pre_action(self, context: HookContext) -> None:
        """Hook-specific pre-action logic. Override in subclasses.

        Args:
            context: Hook context
        """
        ...

    @abstractmethod
    def on_post_action(self, context: HookContext) -> None:
        """Hook-specific post-action logic. Override in subclasses.

        Args:
            context: Hook context
        """
        ...
    
    def cleanup(self) -> None:
        """Called when hook is being removed. Override if needed."""
        pass
    
    @property
    def hook_type(self) -> str:
        """Get the type name of this hook."""
        return self.__class__.__name__
    
    def validate_config(self, config: Dict[str, Any]) -> Optional[str]:
        """Validate hook configuration.
        
        Args:
            config: Configuration to validate
            
        Returns:
            Error message if invalid, None if valid
        """
        return None  # Base implementation assumes all configs are valid
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(initialized={self.initialized}, enabled={self.enabled})"