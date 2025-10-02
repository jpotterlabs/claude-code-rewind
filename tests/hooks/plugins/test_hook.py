"""Test hook implementation for testing hook system."""

from claude_rewind.hooks.base import BaseHook

class TestHook(BaseHook):
    """Test hook implementation."""
    
    hook_type = "TestHook"  # Add hook_type class variable
    
    def __init__(self):
        """Initialize test hook."""
        super().__init__()
        self.pre_called = False
        self.post_called = False
        self.should_cancel = False
        self.should_error = False
    
    def on_initialize(self, config):
        """Initialize hook with config."""
        self.should_cancel = config.get('should_cancel', False)
        self.should_error = config.get('should_error', False)

    def on_pre_action(self, context):
        """Execute pre-action hook."""
        self.pre_called = True
        if self.should_cancel:
            context.cancel("Test cancellation")
        if self.should_error:
            raise ValueError("Test error")

    def on_post_action(self, context):
        """Execute post-action hook."""
        self.post_called = True
        if self.should_error:
            raise ValueError("Test error")