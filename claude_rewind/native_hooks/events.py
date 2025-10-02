"""Event types and data structures for native hooks."""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


class HookEventType(Enum):
    """Native hook event types from Claude Code 2.0."""

    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"
    ERROR = "Error"
    PLAN_CREATED = "PlanCreated"
    PLAN_EXECUTION_START = "PlanExecutionStart"
    PLAN_EXECUTION_END = "PlanExecutionEnd"


@dataclass
class HookEvent:
    """Native hook event data.

    Represents an event fired by Claude Code 2.0's hook system.
    Contains rich context about what Claude is doing.
    """

    event_type: HookEventType
    timestamp: datetime
    session_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    # Common fields extracted from data for convenience
    tool_name: Optional[str] = None
    modified_files: List[Path] = field(default_factory=list)
    prompt_context: Optional[str] = None
    extended_thinking: Optional[str] = None
    confidence_score: Optional[float] = None

    # Subagent-specific fields
    subagent_name: Optional[str] = None
    subagent_type: Optional[str] = None
    parent_session: Optional[str] = None
    delegation_reason: Optional[str] = None

    # Error-specific fields
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None

    # Plan-specific fields
    plan_id: Optional[str] = None
    plan_document: Optional[str] = None
    plan_steps: List[str] = field(default_factory=list)

    @classmethod
    def from_raw_data(cls, event_type_str: str, raw_data: Dict[str, Any]) -> "HookEvent":
        """Create HookEvent from raw hook data.

        Args:
            event_type_str: Event type as string (e.g., "PostToolUse")
            raw_data: Raw event data from Claude Code

        Returns:
            Parsed HookEvent instance
        """
        event_type = HookEventType(event_type_str)

        # Extract timestamp
        timestamp_str = raw_data.get('timestamp')
        timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()

        # Extract session ID
        session_id = raw_data.get('session_id', 'unknown')

        # Create base event
        event = cls(
            event_type=event_type,
            timestamp=timestamp,
            session_id=session_id,
            data=raw_data
        )

        # Extract common fields
        event.tool_name = raw_data.get('tool_name')
        event.prompt_context = raw_data.get('prompt_context')
        event.extended_thinking = raw_data.get('extended_thinking')
        event.confidence_score = raw_data.get('confidence_score')

        # Parse modified files
        if 'modified_files' in raw_data:
            event.modified_files = [Path(f) for f in raw_data['modified_files']]

        # Extract subagent fields
        event.subagent_name = raw_data.get('subagent_name')
        event.subagent_type = raw_data.get('subagent_type')
        event.parent_session = raw_data.get('parent_session')
        event.delegation_reason = raw_data.get('delegation_reason')

        # Extract error fields
        event.error_type = raw_data.get('error_type')
        event.error_message = raw_data.get('error_message')
        event.stack_trace = raw_data.get('stack_trace')

        # Extract plan fields
        event.plan_id = raw_data.get('plan_id')
        event.plan_document = raw_data.get('plan_document')
        event.plan_steps = raw_data.get('plan_steps', [])

        return event

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for storage/logging."""
        return {
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'session_id': self.session_id,
            'tool_name': self.tool_name,
            'modified_files': [str(f) for f in self.modified_files],
            'prompt_context': self.prompt_context,
            'extended_thinking': self.extended_thinking,
            'confidence_score': self.confidence_score,
            'subagent_name': self.subagent_name,
            'subagent_type': self.subagent_type,
            'parent_session': self.parent_session,
            'delegation_reason': self.delegation_reason,
            'error_type': self.error_type,
            'error_message': self.error_message,
            'plan_id': self.plan_id,
            'data': self.data
        }

    def __repr__(self) -> str:
        """String representation for debugging."""
        parts = [f"HookEvent({self.event_type.value}"]
        if self.tool_name:
            parts.append(f" tool={self.tool_name}")
        if self.subagent_name:
            parts.append(f" subagent={self.subagent_name}")
        if self.modified_files:
            parts.append(f" files={len(self.modified_files)}")
        parts.append(")")
        return "".join(parts)
