"""Tests for hook system."""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import yaml

from claude_rewind.hooks.context import HookContext
from claude_rewind.hooks.base import BaseHook
from claude_rewind.hooks.manager import HookManager
from claude_rewind.hooks.plugins.git_hook import GitHook

class TestHook(BaseHook):
    """Test hook implementation."""
    
    pre_called = False
    post_called = False
    should_cancel = False
    should_error = False
    
    def initialize(self, config):
        super().initialize(config)
        self.should_cancel = config.get('should_cancel', False)
        self.should_error = config.get('should_error', False)
    
    def pre_action(self, context):
        super().pre_action(context)
        self.pre_called = True
        if self.should_cancel:
            context.cancel("Test cancellation")
        if self.should_error:
            raise ValueError("Test error")
    
    def post_action(self, context):
        super().post_action(context)
        self.post_called = True
        if self.should_error:
            raise ValueError("Test error")

def test_hook_context():
    """Test hook context functionality."""
    files = [Path("test.py"), Path("other.py")]
    context = HookContext(
        action_type="test",
        files=files,
        project_root=Path.cwd()
    )
    
    assert context.action_type == "test"
    assert context.files == files
    assert not context.is_cancelled
    assert not context.has_errors()
    
    # Test error handling
    context.add_error("Test error")
    assert context.has_errors()
    assert len(context.errors) == 1
    assert context.errors[0] == "Test error"
    
    # Test cancellation
    context.cancel("Test reason")
    assert context.is_cancelled
    assert "Test reason" in context.errors[-1]
    
    # Test modifications
    file = Path("test.py")
    context.add_modification(file, "test mod")
    assert file in context.modifications
    assert context.modifications[file] == "test mod"

def test_hook_manager_initialization():
    """Test hook manager initialization."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        
        # Create test config
        config = {
            'hooks': [
                {
                    'type': 'TestHook',
                    'phase': 'pre_action',
                    'config': {'should_cancel': False}
                },
                {
                    'type': 'TestHook',
                    'phase': 'post_action',
                    'config': {'should_error': False}
                }
            ]
        }
        
        config_path = temp_dir / "hooks.yml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Initialize manager
        manager = HookManager(config_path)
        
        # Check hooks were registered
        assert len(manager.hooks['pre_action']) == 1
        assert len(manager.hooks['post_action']) == 1

def test_hook_execution():
    """Test hook execution flow."""
    manager = HookManager()
    
    # Add test hooks
    pre_hook = TestHook()
    pre_hook.initialize({})
    manager.hooks['pre_action'].append(pre_hook)
    
    post_hook = TestHook()
    post_hook.initialize({})
    manager.hooks['post_action'].append(post_hook)
    
    # Create context
    context = HookContext(
        action_type="test",
        files=[Path("test.py")],
        project_root=Path.cwd()
    )
    
    # Execute hooks
    assert manager.execute_pre_action(context)
    assert pre_hook.pre_called
    assert not context.has_errors()
    
    manager.execute_post_action(context)
    assert post_hook.post_called
    assert not context.has_errors()

def test_hook_cancellation():
    """Test hook cancellation."""
    manager = HookManager()
    
    # Add cancelling hook
    hook = TestHook()
    hook.initialize({'should_cancel': True})
    manager.hooks['pre_action'].append(hook)
    
    # Create context
    context = HookContext(
        action_type="test",
        files=[Path("test.py")],
        project_root=Path.cwd()
    )
    
    # Execute hooks
    assert not manager.execute_pre_action(context)
    assert context.is_cancelled
    assert hook.pre_called

def test_hook_error_handling():
    """Test hook error handling."""
    manager = HookManager()
    
    # Add error-raising hook
    hook = TestHook()
    hook.initialize({'should_error': True})
    manager.hooks['pre_action'].append(hook)
    
    # Create context
    context = HookContext(
        action_type="test",
        files=[Path("test.py")],
        project_root=Path.cwd()
    )
    
    # Execute hooks
    assert manager.execute_pre_action(context)
    assert context.has_errors()
    assert "Test error" in context.errors[0]

def test_git_hook():
    """Test git hook functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        
        # Initialize git repo
        import git
        repo = git.Repo.init(temp_dir)
        
        # Create test file
        test_file = temp_dir / "test.py"
        test_file.write_text("print('test')")
        
        # Initialize git hook
        hook = GitHook()
        hook.initialize({
            'auto_commit': True,
            'commit_message': 'Test: {action_type}'
        })
        
        # Create context
        context = HookContext(
            action_type="test",
            files=[test_file],
            project_root=temp_dir
        )
        
        # Execute hook
        hook.pre_action(context)
        assert 'git_status' in context.metadata
        
        hook.post_action(context)
        assert not context.has_errors()
        assert 'git_commit' in context.metadata
        
        # Verify commit was created
        commit = repo.head.commit
        assert commit.message.startswith('Test: test')
        assert str(test_file.name) in repo.git.ls_files()

def test_hook_cleanup():
    """Test hook cleanup."""
    manager = HookManager()
    
    # Add hooks
    pre_hook = TestHook()
    pre_hook.initialize({})
    manager.hooks['pre_action'].append(pre_hook)
    
    post_hook = TestHook()
    post_hook.initialize({})
    manager.hooks['post_action'].append(post_hook)
    
    # Test context manager
    with manager:
        context = HookContext(
            action_type="test",
            files=[Path("test.py")],
            project_root=Path.cwd()
        )
        manager.execute_pre_action(context)
        manager.execute_post_action(context)
    
    # Verify cleanup happened
    assert pre_hook.initialized
    assert post_hook.initialized