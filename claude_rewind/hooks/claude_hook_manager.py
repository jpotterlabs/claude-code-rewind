"""Claude Code integration hooks and action interceptor."""

import json
import logging
import os
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import asdict

from ..core.interfaces import IClaudeHookManager
from ..core.models import ActionContext, generate_session_id
from ..core.snapshot_engine import SnapshotEngine


logger = logging.getLogger(__name__)


class ClaudeActionType:
    """Constants for Claude Code action types."""
    EDIT_FILE = "edit_file"
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    MULTI_EDIT = "multi_edit"
    READ_FILE = "read_file"
    RUN_COMMAND = "run_command"
    WRITE_FILE = "write_file"
    NOTEBOOK_EDIT = "notebook_edit"


class ClaudeHookManager(IClaudeHookManager):
    """Manages Claude Code integration and automatic snapshot triggering."""

    def __init__(self, project_root: Path, snapshot_engine: SnapshotEngine,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize Claude hook manager.

        Args:
            project_root: Root directory of the project
            snapshot_engine: Snapshot engine for creating snapshots
            config: Configuration settings
        """
        self.project_root = project_root.resolve()
        self.snapshot_engine = snapshot_engine
        self.config = config or {}

        # Hook management
        self._pre_action_hooks: List[Callable[[ActionContext], None]] = []
        self._post_action_hooks: List[Callable[[ActionContext], None]] = []

        # Session management
        self._current_session_id = None
        self._session_start_time = None
        self._action_count = 0

        # Monitoring state
        self._is_monitoring = False
        self._monitor_thread = None
        self._stop_event = threading.Event()

        # Action context tracking
        self._current_action_context: Optional[ActionContext] = None
        self._recent_actions: List[ActionContext] = []
        self._max_recent_actions = 100

        # Claude Code process monitoring
        self._claude_process_info = None
        self._last_activity_check = 0
        self._activity_check_interval = 1.0  # seconds

        # File change tracking for action correlation
        self._pending_file_changes: Dict[Path, Dict[str, Any]] = {}
        self._change_correlation_window = 5.0  # seconds

        logger.info(f"ClaudeHookManager initialized for project: {project_root}")

    def register_pre_action_hook(self, callback: Callable[[ActionContext], None]) -> None:
        """Register a callback to be called before Claude actions.

        Args:
            callback: Function to call with ActionContext
        """
        self._pre_action_hooks.append(callback)
        logger.debug(f"Registered pre-action hook: {callback.__name__}")

    def register_post_action_hook(self, callback: Callable[[ActionContext], None]) -> None:
        """Register a callback to be called after Claude actions.

        Args:
            callback: Function to call with ActionContext
        """
        self._post_action_hooks.append(callback)
        logger.debug(f"Registered post-action hook: {callback.__name__}")

    def get_current_action_context(self) -> Optional[ActionContext]:
        """Get context for the currently executing action.

        Returns:
            Current action context or None if no action is executing
        """
        return self._current_action_context

    def start_monitoring(self) -> bool:
        """Start monitoring Claude Code actions.

        Returns:
            True if monitoring started successfully
        """
        if self._is_monitoring:
            logger.warning("Claude monitoring is already active")
            return True

        try:
            # Start new session
            self._start_new_session()

            # Setup monitoring thread
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self._monitor_thread.start()

            self._is_monitoring = True
            logger.info("Started Claude Code monitoring")

            # Register built-in snapshot hook
            self.register_post_action_hook(self._create_snapshot_hook)

            return True

        except Exception as e:
            logger.error(f"Failed to start Claude monitoring: {e}")
            return False

    def stop_monitoring(self) -> bool:
        """Stop monitoring Claude Code actions.

        Returns:
            True if monitoring stopped successfully
        """
        if not self._is_monitoring:
            return True

        try:
            # Signal monitoring thread to stop
            self._stop_event.set()

            # Wait for thread to finish
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=5.0)

            self._is_monitoring = False
            self._current_session_id = None

            logger.info("Stopped Claude Code monitoring")
            return True

        except Exception as e:
            logger.error(f"Failed to stop Claude monitoring: {e}")
            return False

    def _start_new_session(self) -> None:
        """Start a new Claude Code session."""
        self._current_session_id = generate_session_id()
        self._session_start_time = datetime.now()
        self._action_count = 0
        self._recent_actions.clear()

        logger.info(f"Started new Claude session: {self._current_session_id}")

    def _monitoring_loop(self) -> None:
        """Main monitoring loop that runs in background thread."""
        logger.debug("Claude monitoring loop started")

        while not self._stop_event.is_set():
            try:
                # Check for Claude Code activity
                self._check_claude_activity()

                # Process any pending file changes
                self._process_pending_changes()

                # Clean up old recent actions
                self._cleanup_recent_actions()

                # Sleep before next check
                self._stop_event.wait(self._activity_check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                # Continue monitoring even if there's an error
                self._stop_event.wait(1.0)

        logger.debug("Claude monitoring loop stopped")

    def _check_claude_activity(self) -> None:
        """Check for Claude Code process activity and detect actions."""
        current_time = time.time()

        # Skip if we've checked recently
        if current_time - self._last_activity_check < self._activity_check_interval:
            return

        self._last_activity_check = current_time

        # Method 1: Check for Claude Code process
        claude_active = self._is_claude_process_active()

        # Method 2: Monitor Claude Code working directory changes
        claude_workspace = self._detect_claude_workspace()

        # Method 3: Check for Claude-specific environment variables or files
        claude_context = self._detect_claude_context()

        if claude_active or claude_workspace or claude_context:
            # Claude is active, start monitoring for specific actions
            self._monitor_active_claude_session()

    def _is_claude_process_active(self) -> bool:
        """Check if Claude Code process is currently running.

        Returns:
            True if Claude Code process is detected
        """
        try:
            # Look for Claude Code in running processes
            result = subprocess.run(
                ['pgrep', '-f', 'claude'],
                capture_output=True, text=True, timeout=5
            )

            if result.returncode == 0 and result.stdout.strip():
                process_ids = result.stdout.strip().split('\n')
                logger.debug(f"Found Claude processes: {process_ids}")
                return True

        except (subprocess.SubprocessError, subprocess.TimeoutExpired) as e:
            logger.debug(f"Process check failed: {e}")

        return False

    def _detect_claude_workspace(self) -> bool:
        """Detect if we're in a Claude Code workspace.

        Returns:
            True if Claude workspace indicators are found
        """
        # Check for Claude-specific files or directories
        claude_indicators = [
            '.claude',
            '.claude-code',
            'claude.md',
            'CLAUDE.md'
        ]

        for indicator in claude_indicators:
            if (self.project_root / indicator).exists():
                logger.debug(f"Found Claude workspace indicator: {indicator}")
                return True

        return False

    def _detect_claude_context(self) -> bool:
        """Detect Claude Code context from environment or special markers.

        Returns:
            True if Claude context is detected
        """
        # Check environment variables that might indicate Claude Code
        claude_env_vars = [
            'CLAUDE_SESSION',
            'CLAUDE_CODE_SESSION',
            'ANTHROPIC_API_KEY'
        ]

        for var in claude_env_vars:
            if os.getenv(var):
                logger.debug(f"Found Claude environment variable: {var}")
                return True

        # Check for recent Claude-related file modifications
        try:
            claude_files = list(self.project_root.glob('**/claude*'))
            claude_files.extend(list(self.project_root.glob('**/*claude*')))

            recent_threshold = time.time() - 300  # 5 minutes

            for file_path in claude_files:
                if file_path.is_file():
                    try:
                        if file_path.stat().st_mtime > recent_threshold:
                            logger.debug(f"Found recently modified Claude file: {file_path}")
                            return True
                    except OSError:
                        continue

        except Exception as e:
            logger.debug(f"Error checking Claude files: {e}")

        return False

    def _monitor_active_claude_session(self) -> None:
        """Monitor an active Claude session for specific actions."""
        # This is where we would implement the core action detection
        # For now, we'll use file system changes as a proxy for Claude actions

        try:
            # Detect file changes that might be Claude actions
            recent_changes = self._detect_recent_file_changes()

            for change in recent_changes:
                # Try to correlate file change with Claude action
                action_context = self._correlate_change_to_action(change)

                if action_context:
                    # This looks like a Claude action
                    self._handle_detected_action(action_context)

        except Exception as e:
            logger.error(f"Error monitoring Claude session: {e}")

    def _detect_recent_file_changes(self) -> List[Dict[str, Any]]:
        """Detect recent file changes that might be Claude actions.

        Returns:
            List of file change information
        """
        changes = []
        current_time = time.time()
        recent_threshold = current_time - self._change_correlation_window

        try:
            # Scan project files for recent changes
            for file_path in self.project_root.rglob('*'):
                if not file_path.is_file():
                    continue

                # Skip files we should ignore
                if self._should_ignore_file(file_path):
                    continue

                try:
                    stat = file_path.stat()

                    # Check if file was modified recently
                    if stat.st_mtime > recent_threshold:
                        relative_path = file_path.relative_to(self.project_root)

                        change_info = {
                            'path': relative_path,
                            'full_path': file_path,
                            'modification_time': stat.st_mtime,
                            'size': stat.st_size,
                            'detected_at': current_time
                        }

                        changes.append(change_info)

                except OSError as e:
                    logger.debug(f"Error checking file {file_path}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error detecting file changes: {e}")

        return changes

    def _correlate_change_to_action(self, change: Dict[str, Any]) -> Optional[ActionContext]:
        """Correlate a file change to a Claude Code action.

        Args:
            change: File change information

        Returns:
            ActionContext if this appears to be a Claude action, None otherwise
        """
        file_path = change['path']
        full_path = change['full_path']

        # Heuristics to determine if this is likely a Claude action
        is_claude_action = False
        action_type = "file_change"
        confidence = 0.5

        # Check file type - code files are more likely to be Claude actions
        if self._is_code_file(full_path):
            confidence += 0.2

        # Check file size - very small or very large changes might not be Claude
        file_size = change.get('size', 0)
        if 10 < file_size < 100000:  # Between 10 bytes and 100KB
            confidence += 0.1

        # Check if multiple files were changed around the same time
        recent_changes = len([c for c in self._pending_file_changes.values()
                             if abs(c.get('detected_at', 0) - change['detected_at']) < 2.0])
        if recent_changes > 1:
            confidence += 0.2
            action_type = "multi_file_change"

        # Check for specific patterns that indicate Claude actions
        try:
            if full_path.exists() and full_path.suffix in ['.py', '.js', '.ts', '.java', '.cpp']:
                content = full_path.read_text(encoding='utf-8', errors='ignore')

                # Look for patterns that suggest AI-generated code
                ai_patterns = [
                    '# Generated by', '// Generated by',
                    'TODO:', 'FIXME:', '# Fix:', '// Fix:',
                    'def ', 'function ', 'class ', 'interface ',
                    'import ', 'from ', 'require('
                ]

                pattern_matches = sum(1 for pattern in ai_patterns if pattern in content)
                if pattern_matches >= 2:
                    confidence += 0.3

        except Exception as e:
            logger.debug(f"Error analyzing file content: {e}")

        # Determine action type based on file state
        if not full_path.exists():
            action_type = ClaudeActionType.DELETE_FILE
            confidence += 0.2
        elif file_path not in self._get_known_files():
            action_type = ClaudeActionType.CREATE_FILE
            confidence += 0.3
        else:
            action_type = ClaudeActionType.EDIT_FILE
            confidence += 0.1

        # Only treat as Claude action if confidence is high enough
        if confidence > 0.7:
            is_claude_action = True

        if is_claude_action:
            # Create action context
            context = ActionContext(
                action_type=action_type,
                timestamp=datetime.fromtimestamp(change['modification_time']),
                prompt_context=f"Detected {action_type} on {file_path}",
                affected_files=[file_path],
                tool_name="claude_code",
                session_id=self._current_session_id
            )

            logger.debug(f"Correlated file change to Claude action: {action_type} on {file_path} (confidence: {confidence:.2f})")
            return context

        return None

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if a file is likely a code file.

        Args:
            file_path: Path to check

        Returns:
            True if this appears to be a code file
        """
        code_extensions = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h',
            '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt', '.scala',
            '.html', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
            '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg',
            '.sql', '.sh', '.bash', '.zsh', '.ps1', '.bat', '.cmd',
            '.md', '.rst', '.txt', '.log'
        }

        return file_path.suffix.lower() in code_extensions

    def _get_known_files(self) -> Set[Path]:
        """Get set of files that were known in the last snapshot.

        Returns:
            Set of known file paths
        """
        # This would ideally come from the last snapshot
        # For now, we'll use a simple heuristic
        known_files = set()

        try:
            # Get files that existed more than a minute ago
            threshold = time.time() - 60

            for file_path in self.project_root.rglob('*'):
                if file_path.is_file() and not self._should_ignore_file(file_path):
                    try:
                        if file_path.stat().st_mtime < threshold:
                            known_files.add(file_path.relative_to(self.project_root))
                    except OSError:
                        continue

        except Exception as e:
            logger.debug(f"Error getting known files: {e}")

        return known_files

    def _should_ignore_file(self, file_path: Path) -> bool:
        """Check if a file should be ignored for monitoring.

        Args:
            file_path: Path to check

        Returns:
            True if file should be ignored
        """
        # Use similar logic to snapshot engine
        ignore_patterns = {
            '.git', '.svn', '.hg',
            '__pycache__', '.pytest_cache',
            'node_modules', '.npm',
            '.vscode', '.idea',
            'venv', '.venv', 'env',
            'target', 'build', 'dist',
            '.claude-rewind'
        }

        # Check if any parent directory should be ignored
        for part in file_path.parts:
            if part in ignore_patterns or part.startswith('.'):
                return True

        # Check file extensions to ignore
        ignore_extensions = {'.pyc', '.pyo', '.pyd', '.log', '.tmp', '.temp'}
        if file_path.suffix.lower() in ignore_extensions:
            return True

        return False

    def _handle_detected_action(self, action_context: ActionContext) -> None:
        """Handle a detected Claude action.

        Args:
            action_context: Context of the detected action
        """
        try:
            # Set current action context
            self._current_action_context = action_context

            # Call pre-action hooks
            for hook in self._pre_action_hooks:
                try:
                    hook(action_context)
                except Exception as e:
                    logger.error(f"Error in pre-action hook {hook.__name__}: {e}")

            # Log the action
            logger.info(f"Detected Claude action: {action_context.action_type} on {action_context.affected_files}")

            # Add to recent actions
            self._recent_actions.append(action_context)
            if len(self._recent_actions) > self._max_recent_actions:
                self._recent_actions.pop(0)

            self._action_count += 1

            # Call post-action hooks (including snapshot creation)
            for hook in self._post_action_hooks:
                try:
                    hook(action_context)
                except Exception as e:
                    logger.error(f"Error in post-action hook {hook.__name__}: {e}")

        except Exception as e:
            logger.error(f"Error handling detected action: {e}")
        finally:
            # Clear current action context
            self._current_action_context = None

    def _create_snapshot_hook(self, action_context: ActionContext) -> None:
        """Built-in hook to create snapshots for Claude actions.

        Args:
            action_context: Context of the action that triggered this hook
        """
        try:
            # Check if we should create a snapshot for this action
            if not self._should_create_snapshot(action_context):
                logger.debug(f"Skipping snapshot for action: {action_context.action_type}")
                return

            # Create snapshot
            snapshot_id = self.snapshot_engine.create_snapshot(action_context)

            logger.info(f"Created snapshot {snapshot_id} for Claude action: {action_context.action_type}")

        except Exception as e:
            logger.error(f"Failed to create snapshot for Claude action: {e}")

    def _should_create_snapshot(self, action_context: ActionContext) -> bool:
        """Determine if we should create a snapshot for this action.

        Args:
            action_context: Action context to evaluate

        Returns:
            True if snapshot should be created
        """
        # Check configuration
        hooks_config = self.config.get('hooks', {})
        if not hooks_config.get('auto_snapshot_enabled', True):
            return False

        # Don't snapshot read-only actions
        if action_context.action_type == ClaudeActionType.READ_FILE:
            return False

        # Always snapshot file modifications
        if action_context.action_type in [
            ClaudeActionType.EDIT_FILE,
            ClaudeActionType.CREATE_FILE,
            ClaudeActionType.DELETE_FILE,
            ClaudeActionType.MULTI_EDIT,
            ClaudeActionType.WRITE_FILE
        ]:
            return True

        # Snapshot command executions that might modify files
        if action_context.action_type == ClaudeActionType.RUN_COMMAND:
            return True

        return True  # Default to creating snapshots

    def _process_pending_changes(self) -> None:
        """Process any pending file changes that haven't been correlated yet."""
        current_time = time.time()
        expired_threshold = current_time - (self._change_correlation_window * 2)

        # Remove expired pending changes
        expired_keys = [
            key for key, change in self._pending_file_changes.items()
            if change.get('detected_at', 0) < expired_threshold
        ]

        for key in expired_keys:
            del self._pending_file_changes[key]

    def _cleanup_recent_actions(self) -> None:
        """Clean up old recent actions."""
        current_time = time.time()
        cutoff_time = current_time - 3600  # Keep actions from last hour

        self._recent_actions = [
            action for action in self._recent_actions
            if action.timestamp.timestamp() > cutoff_time
        ]

    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about the current Claude session.

        Returns:
            Dictionary with session statistics
        """
        stats = {
            'session_id': self._current_session_id,
            'session_start_time': self._session_start_time.isoformat() if self._session_start_time else None,
            'action_count': self._action_count,
            'recent_actions_count': len(self._recent_actions),
            'is_monitoring': self._is_monitoring,
            'pre_hooks_count': len(self._pre_action_hooks),
            'post_hooks_count': len(self._post_action_hooks)
        }

        if self._session_start_time:
            session_duration = datetime.now() - self._session_start_time
            stats['session_duration_seconds'] = session_duration.total_seconds()

        return stats

    def get_recent_actions(self, limit: int = 10) -> List[ActionContext]:
        """Get recent Claude actions.

        Args:
            limit: Maximum number of actions to return

        Returns:
            List of recent action contexts
        """
        return self._recent_actions[-limit:] if self._recent_actions else []