"""Event handlers for native hooks."""

import logging
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from .events import HookEvent, HookEventType
from ..core.snapshot_engine import SnapshotEngine
from ..storage.database import DatabaseManager
from ..storage.file_store import FileStore
from ..core.config import ConfigManager

logger = logging.getLogger(__name__)


class NativeHookDispatcher:
    """Dispatcher for native hook events.

    Routes hook events to appropriate handlers and creates snapshots.
    """

    def __init__(self, project_root: Path):
        """Initialize hook dispatcher.

        Args:
            project_root: Project root directory
        """
        self.project_root = project_root

        # Initialize snapshot engine
        config_manager = ConfigManager(project_root)
        config = config_manager.load_config()

        rewind_dir = project_root / ".claude-rewind"
        self.snapshot_engine = SnapshotEngine(
            project_root,
            rewind_dir,
            config.performance,
            config.storage,
            config.git_integration
        )

        # Handler registry
        self._handlers: Dict[HookEventType, Callable[[HookEvent], None]] = {
            HookEventType.SESSION_START: self._handle_session_start,
            HookEventType.SESSION_END: self._handle_session_end,
            HookEventType.PRE_TOOL_USE: self._handle_pre_tool_use,
            HookEventType.POST_TOOL_USE: self._handle_post_tool_use,
            HookEventType.SUBAGENT_START: self._handle_subagent_start,
            HookEventType.SUBAGENT_STOP: self._handle_subagent_stop,
            HookEventType.ERROR: self._handle_error,
        }

        # Session tracking
        self._current_session_id: Optional[str] = None
        self._session_start_time: Optional[datetime] = None

    def dispatch(self, event: HookEvent) -> None:
        """Dispatch event to appropriate handler.

        Args:
            event: Hook event to process
        """
        handler = self._handlers.get(event.event_type)

        if handler is None:
            logger.warning(f"No handler for event type: {event.event_type}")
            return

        try:
            logger.info(f"Dispatching {event}")
            handler(event)
        except Exception as e:
            logger.exception(f"Handler failed for {event}: {e}")

    def _handle_session_start(self, event: HookEvent) -> None:
        """Handle SessionStart event.

        Args:
            event: Session start event
        """
        self._current_session_id = event.session_id
        self._session_start_time = event.timestamp

        logger.info(f"Session started: {event.session_id}")

        # Create initial session snapshot
        try:
            snapshot_id = self.snapshot_engine.create_snapshot(
                description=f"Session start: {event.session_id}",
                tags=['session-start', f'session:{event.session_id}']
            )
            logger.info(f"Created session start snapshot: {snapshot_id}")
        except Exception as e:
            logger.error(f"Failed to create session start snapshot: {e}")

    def _handle_session_end(self, event: HookEvent) -> None:
        """Handle SessionEnd event.

        Args:
            event: Session end event
        """
        logger.info(f"Session ended: {event.session_id}")

        # Create final session snapshot
        try:
            duration = None
            if self._session_start_time:
                duration = (event.timestamp - self._session_start_time).total_seconds()

            description = f"Session end: {event.session_id}"
            if duration:
                description += f" (duration: {duration:.1f}s)"

            snapshot_id = self.snapshot_engine.create_snapshot(
                description=description,
                tags=['session-end', f'session:{event.session_id}']
            )
            logger.info(f"Created session end snapshot: {snapshot_id}")
        except Exception as e:
            logger.error(f"Failed to create session end snapshot: {e}")

        # Reset session tracking
        self._current_session_id = None
        self._session_start_time = None

    def _handle_pre_tool_use(self, event: HookEvent) -> None:
        """Handle PreToolUse event.

        Args:
            event: Pre-tool-use event
        """
        # For now, just log. Could be used for diff calculation later.
        logger.debug(f"Pre-tool-use: {event.tool_name}")

    def _handle_post_tool_use(self, event: HookEvent) -> None:
        """Handle PostToolUse event - creates automatic snapshot.

        Args:
            event: Post-tool-use event
        """
        tool_name = event.tool_name or "unknown_tool"

        # Build description
        description = f"{tool_name}"
        if event.prompt_context:
            # Truncate long prompts
            prompt = event.prompt_context[:100]
            if len(event.prompt_context) > 100:
                prompt += "..."
            description += f": {prompt}"

        # Build tags
        tags = [
            'auto',
            f'tool:{tool_name}',
            f'session:{event.session_id}'
        ]

        if event.confidence_score is not None:
            tags.append(f'confidence:{event.confidence_score:.2f}')

        # Create snapshot with rich context
        try:
            snapshot_id = self.snapshot_engine.create_snapshot(
                description=description,
                tags=tags
            )

            logger.info(f"Created snapshot {snapshot_id} for {tool_name}")

            # Store extended thinking and context in snapshot metadata
            # (This would require enhancing SnapshotEngine to store custom metadata)

        except Exception as e:
            logger.error(f"Failed to create snapshot for {tool_name}: {e}")

    def _handle_subagent_start(self, event: HookEvent) -> None:
        """Handle SubagentStart event.

        Args:
            event: Subagent start event
        """
        subagent_name = event.subagent_name or "unknown"
        logger.info(f"Subagent started: {subagent_name}")

        # Create subagent delegation snapshot
        try:
            description = f"Subagent {subagent_name} started"
            if event.delegation_reason:
                description += f": {event.delegation_reason}"

            tags = [
                'subagent-start',
                f'subagent:{subagent_name}',
                f'session:{event.session_id}'
            ]

            if event.subagent_type:
                tags.append(f'type:{event.subagent_type}')

            snapshot_id = self.snapshot_engine.create_snapshot(
                description=description,
                tags=tags
            )

            logger.info(f"Created subagent start snapshot: {snapshot_id}")

        except Exception as e:
            logger.error(f"Failed to create subagent start snapshot: {e}")

    def _handle_subagent_stop(self, event: HookEvent) -> None:
        """Handle SubagentStop event - captures subagent's work.

        Args:
            event: Subagent stop event
        """
        subagent_name = event.subagent_name or "unknown"
        logger.info(f"Subagent stopped: {subagent_name}")

        # Create snapshot of subagent's work
        try:
            description = f"Subagent {subagent_name} completed"

            tags = [
                'subagent-stop',
                f'subagent:{subagent_name}',
                f'session:{event.session_id}'
            ]

            if event.subagent_type:
                tags.append(f'type:{event.subagent_type}')

            if event.parent_session:
                tags.append(f'parent:{event.parent_session}')

            snapshot_id = self.snapshot_engine.create_snapshot(
                description=description,
                tags=tags
            )

            logger.info(f"Created subagent stop snapshot: {snapshot_id}")

        except Exception as e:
            logger.error(f"Failed to create subagent stop snapshot: {e}")

    def _handle_error(self, event: HookEvent) -> None:
        """Handle Error event - auto-suggests rollback.

        Args:
            event: Error event
        """
        error_type = event.error_type or "unknown"
        error_msg = event.error_message or "No message"

        logger.warning(f"Error detected: {error_type} - {error_msg}")

        # Create error snapshot
        try:
            description = f"Error: {error_type}"

            tags = [
                'error',
                f'error-type:{error_type}',
                f'session:{event.session_id}'
            ]

            snapshot_id = self.snapshot_engine.create_snapshot(
                description=description,
                tags=tags
            )

            logger.info(f"Created error snapshot: {snapshot_id}")

            # TODO: Implement smart rollback suggestions
            # This would analyze recent snapshots and suggest which one to rollback to
            # For now, just log a suggestion
            recent_snapshots = self.snapshot_engine.list_snapshots(limit=5)
            if recent_snapshots:
                last_snapshot = recent_snapshots[0]
                logger.info(f"💡 Suggestion: Consider rolling back to {last_snapshot['id']}")

        except Exception as e:
            logger.exception(f"Failed to create error snapshot: {e}")


def handle_hook_event(event_type_str: str, event_data_json: str, project_root: Optional[Path] = None) -> int:
    """Handle a hook event from command line.

    This is the entry point called by Claude Code when hooks fire.

    Args:
        event_type_str: Event type (e.g., "PostToolUse")
        event_data_json: JSON string with event data
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if project_root is None:
        project_root = Path.cwd()

    try:
        # Parse event data
        event_data = json.loads(event_data_json)

        # Create event object
        event = HookEvent.from_raw_data(event_type_str, event_data)

        # Dispatch to handler
        dispatcher = NativeHookDispatcher(project_root)
        dispatcher.dispatch(event)

        return 0

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse event data: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Hook handler failed: {e}")
        return 1
