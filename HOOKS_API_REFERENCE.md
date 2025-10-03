# Hooks API Reference

**Technical Reference for Claude Code Rewind Native Hooks System**

---

## Table of Contents

- [Module Structure](#module-structure)
- [Event Types](#event-types)
- [Data Structures](#data-structures)
- [Handler System](#handler-system)
- [Registration System](#registration-system)
- [Extension Guide](#extension-guide)

---

## Module Structure

```
claude_rewind/native_hooks/
├── __init__.py          # Module exports
├── events.py            # Event types and HookEvent dataclass
├── handlers.py          # Event dispatcher and handlers
└── registration.py      # Hook registration/management
```

### Exports

```python
from claude_rewind.native_hooks import (
    # Registration functions
    register_native_hooks,
    unregister_hooks,
    get_registered_hooks,
    is_hooks_registered,

    # Event handling
    NativeHookDispatcher,
    handle_hook_event,

    # Event types
    HookEvent,
    HookEventType,
)
```

---

## Event Types

### HookEventType Enum

Defined in `claude_rewind/native_hooks/events.py:10-23`

```python
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
```

### Event Type Details

| Event Type | String Value | Fires When | Creates Snapshot |
|------------|--------------|------------|------------------|
| `SESSION_START` | "SessionStart" | Claude Code session begins | Yes |
| `SESSION_END` | "SessionEnd" | Claude Code session ends | Yes |
| `PRE_TOOL_USE` | "PreToolUse" | Before tool execution | No (logged only) |
| `POST_TOOL_USE` | "PostToolUse" | After successful tool use | Yes ⭐ |
| `SUBAGENT_START` | "SubagentStart" | Subagent delegation | Yes |
| `SUBAGENT_STOP` | "SubagentStop" | Subagent completion | Yes ⭐ |
| `ERROR` | "Error" | Error occurs | Yes |
| `PLAN_CREATED` | "PlanCreated" | Plan mode creates plan | Future |
| `PLAN_EXECUTION_START` | "PlanExecutionStart" | Plan execution begins | Future |
| `PLAN_EXECUTION_END` | "PlanExecutionEnd" | Plan execution ends | Future |

---

## Data Structures

### HookEvent Dataclass

Defined in `claude_rewind/native_hooks/events.py:25-149`

```python
@dataclass
class HookEvent:
    """Native hook event data.

    Represents an event fired by Claude Code 2.0's hook system.
    Contains rich context about what Claude is doing.
    """

    # Core fields (always present)
    event_type: HookEventType
    timestamp: datetime
    session_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    # Common fields (extracted from data for convenience)
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

    # Plan-specific fields (future)
    plan_id: Optional[str] = None
    plan_document: Optional[str] = None
    plan_steps: List[str] = field(default_factory=list)
```

### Field Descriptions

#### Core Fields

| Field | Type | Description | Always Present |
|-------|------|-------------|----------------|
| `event_type` | `HookEventType` | Type of event | Yes |
| `timestamp` | `datetime` | When event occurred | Yes |
| `session_id` | `str` | Claude session ID | Yes |
| `data` | `Dict[str, Any]` | Raw event data from Claude | Yes |

#### Common Fields

| Field | Type | Description | Present When |
|-------|------|-------------|--------------|
| `tool_name` | `Optional[str]` | Tool used (Edit, Write, Bash, etc.) | Tool events |
| `modified_files` | `List[Path]` | Files affected | Tool events |
| `prompt_context` | `Optional[str]` | User's prompt | Tool events |
| `extended_thinking` | `Optional[str]` | Claude's internal reasoning | Tool events (if available) |
| `confidence_score` | `Optional[float]` | Confidence level (0.0-1.0) | Tool events (if available) |

#### Subagent Fields

| Field | Type | Description | Present When |
|-------|------|-------------|--------------|
| `subagent_name` | `Optional[str]` | Name of subagent | Subagent events |
| `subagent_type` | `Optional[str]` | Type of subagent | Subagent events |
| `parent_session` | `Optional[str]` | Parent session ID | Subagent events |
| `delegation_reason` | `Optional[str]` | Why subagent invoked | SubagentStart |

#### Error Fields

| Field | Type | Description | Present When |
|-------|------|-------------|--------------|
| `error_type` | `Optional[str]` | Type of error | Error events |
| `error_message` | `Optional[str]` | Error message | Error events |
| `stack_trace` | `Optional[str]` | Stack trace | Error events |

#### Plan Fields (Future)

| Field | Type | Description | Present When |
|-------|------|-------------|--------------|
| `plan_id` | `Optional[str]` | Plan identifier | Plan events |
| `plan_document` | `Optional[str]` | Plan markdown | PlanCreated |
| `plan_steps` | `List[str]` | Plan steps | Plan events |

### Methods

#### `HookEvent.from_raw_data()`

```python
@classmethod
def from_raw_data(
    cls,
    event_type_str: str,
    raw_data: Dict[str, Any]
) -> "HookEvent":
    """Create HookEvent from raw hook data.

    Args:
        event_type_str: Event type as string (e.g., "PostToolUse")
        raw_data: Raw event data from Claude Code

    Returns:
        Parsed HookEvent instance

    Raises:
        ValueError: If event_type_str is not a valid HookEventType
    """
```

**Example:**
```python
event = HookEvent.from_raw_data(
    "PostToolUse",
    {
        "timestamp": "2025-10-02T14:30:00",
        "session_id": "abc123",
        "tool_name": "Edit",
        "prompt_context": "Fix login bug",
        "modified_files": ["src/auth.py"],
        "confidence_score": 0.87
    }
)
```

#### `HookEvent.to_dict()`

```python
def to_dict(self) -> Dict[str, Any]:
    """Convert event to dictionary for storage/logging.

    Returns:
        Dictionary representation of event
    """
```

**Example:**
```python
event_dict = event.to_dict()
# {
#     'event_type': 'PostToolUse',
#     'timestamp': '2025-10-02T14:30:00',
#     'session_id': 'abc123',
#     'tool_name': 'Edit',
#     ...
# }
```

#### `HookEvent.__repr__()`

```python
def __repr__(self) -> str:
    """String representation for debugging."""
```

**Example:**
```python
print(event)
# HookEvent(PostToolUse tool=Edit files=1)
```

---

## Handler System

### NativeHookDispatcher Class

Defined in `claude_rewind/native_hooks/handlers.py:19-288`

```python
class NativeHookDispatcher:
    """Dispatcher for native hook events.

    Routes hook events to appropriate handlers and creates snapshots.
    """

    def __init__(self, project_root: Path):
        """Initialize hook dispatcher.

        Args:
            project_root: Project root directory
        """
```

### Initialization

```python
dispatcher = NativeHookDispatcher(Path("/path/to/project"))
```

**What happens:**
1. Loads project configuration from `.claude-rewind/config.yaml`
2. Initializes `SnapshotEngine` with project settings
3. Registers event handlers for each `HookEventType`
4. Initializes session tracking

### Handler Registry

```python
self._handlers: Dict[HookEventType, Callable[[HookEvent], None]] = {
    HookEventType.SESSION_START: self._handle_session_start,
    HookEventType.SESSION_END: self._handle_session_end,
    HookEventType.PRE_TOOL_USE: self._handle_pre_tool_use,
    HookEventType.POST_TOOL_USE: self._handle_post_tool_use,
    HookEventType.SUBAGENT_START: self._handle_subagent_start,
    HookEventType.SUBAGENT_STOP: self._handle_subagent_stop,
    HookEventType.ERROR: self._handle_error,
}
```

### Dispatch Method

```python
def dispatch(self, event: HookEvent) -> None:
    """Dispatch event to appropriate handler.

    Args:
        event: Hook event to process

    Raises:
        Exception: If handler fails (caught and logged)
    """
```

**Example:**
```python
event = HookEvent.from_raw_data("PostToolUse", event_data)
dispatcher.dispatch(event)
```

### Handler Methods

#### `_handle_session_start()`

**Location**: `handlers.py:79-98`

```python
def _handle_session_start(self, event: HookEvent) -> None:
    """Handle SessionStart event.

    Args:
        event: Session start event
    """
```

**Behavior:**
- Stores `session_id` and start time for tracking
- Creates snapshot with tags: `['session-start', 'session:{id}']`
- Description: `"Session start: {session_id}"`

---

#### `_handle_session_end()`

**Location**: `handlers.py:100-128`

```python
def _handle_session_end(self, event: HookEvent) -> None:
    """Handle SessionEnd event.

    Args:
        event: Session end event
    """
```

**Behavior:**
- Calculates session duration if start time available
- Creates snapshot with tags: `['session-end', 'session:{id}']`
- Description: `"Session end: {session_id} (duration: {seconds}s)"`
- Resets session tracking

---

#### `_handle_pre_tool_use()`

**Location**: `handlers.py:130-137`

```python
def _handle_pre_tool_use(self, event: HookEvent) -> None:
    """Handle PreToolUse event.

    Args:
        event: Pre-tool-use event
    """
```

**Behavior:**
- Currently only logs event (does not create snapshot)
- Future: Could calculate precise diffs by comparing pre/post states

---

#### `_handle_post_tool_use()` ⭐

**Location**: `handlers.py:139-179`

```python
def _handle_post_tool_use(self, event: HookEvent) -> None:
    """Handle PostToolUse event - creates automatic snapshot.

    Args:
        event: Post-tool-use event
    """
```

**Behavior:**
1. Extracts tool name and prompt context
2. Truncates long prompts to 100 chars
3. Builds description: `"{tool_name}: {prompt}"`
4. Creates tags:
   - `'auto'` - Automatic snapshot
   - `'tool:{tool_name}'` - Tool attribution
   - `'session:{session_id}'` - Session tracking
   - `'confidence:{score}'` - If confidence available
5. Creates snapshot via `SnapshotEngine`
6. Logs outcome

**This is the primary hook** for automatic snapshot creation.

---

#### `_handle_subagent_start()`

**Location**: `handlers.py:181-213`

```python
def _handle_subagent_start(self, event: HookEvent) -> None:
    """Handle SubagentStart event.

    Args:
        event: Subagent start event
    """
```

**Behavior:**
- Creates snapshot with description: `"Subagent {name} started: {reason}"`
- Tags:
  - `'subagent-start'`
  - `'subagent:{name}'`
  - `'type:{type}'` (if available)
  - `'session:{session_id}'`

---

#### `_handle_subagent_stop()` ⭐

**Location**: `handlers.py:215-248`

```python
def _handle_subagent_stop(self, event: HookEvent) -> None:
    """Handle SubagentStop event - captures subagent's work.

    Args:
        event: Subagent stop event
    """
```

**Behavior:**
- Creates snapshot with description: `"Subagent {name} completed"`
- Tags:
  - `'subagent-stop'`
  - `'subagent:{name}'`
  - `'type:{type}'` (if available)
  - `'parent:{parent_session}'` (if available)
  - `'session:{session_id}'`

**Allows independent rollback of subagent changes.**

---

#### `_handle_error()` ⭐

**Location**: `handlers.py:250-287`

```python
def _handle_error(self, event: HookEvent) -> None:
    """Handle Error event - auto-suggests rollback.

    Args:
        event: Error event
    """
```

**Behavior:**
1. Creates snapshot with description: `"Error: {error_type}"`
2. Tags:
   - `'error'`
   - `'error-type:{type}'`
   - `'session:{session_id}'`
3. Retrieves last 5 snapshots
4. Suggests most recent non-error snapshot for rollback
5. Logs suggestion: `"💡 Suggestion: Consider rolling back to {snapshot_id}"`

**Enables automatic rollback suggestions.**

---

### Entry Point Function

**Location**: `handlers.py:290-324`

```python
def handle_hook_event(
    event_type_str: str,
    event_data_json: str,
    project_root: Optional[Path] = None
) -> int:
    """Handle a hook event from command line.

    This is the entry point called by Claude Code when hooks fire.

    Args:
        event_type_str: Event type (e.g., "PostToolUse")
        event_data_json: JSON string with event data
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
```

**Usage:**
```bash
claude-rewind hook-handler post-tool-use '{"session_id":"abc",...}'
```

**Called by Claude Code** via `.claude/settings.json` configuration.

---

## Registration System

### Functions

#### `register_native_hooks()`

**Location**: `registration.py:78-151`

```python
def register_native_hooks(project_root: Optional[Path] = None) -> None:
    """Register Claude Code Rewind hooks in .claude/settings.json.

    This configures Claude Code 2.0 to call claude-rewind when events fire.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Raises:
        HookRegistrationError: If registration fails
    """
```

**Behavior:**
1. Loads existing `.claude/settings.json` (or creates empty dict)
2. Creates hook configuration for all 7 hooks
3. Merges with existing hooks (preserves user's custom hooks)
4. Writes updated settings back to file
5. Logs success

**Hook Configuration Template:**
```python
{
    "SessionStart": {
        "command": "claude-rewind",
        "args": ["hook-handler", "session-start"],
        "background": True,
        "description": "Initialize Claude Code Rewind session tracking"
    },
    # ... 6 more hooks
}
```

---

#### `unregister_hooks()`

**Location**: `registration.py:154-185`

```python
def unregister_hooks(project_root: Optional[Path] = None) -> None:
    """Remove Claude Code Rewind hooks from .claude/settings.json.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Raises:
        HookRegistrationError: If unregistration fails
    """
```

**Behavior:**
1. Loads `.claude/settings.json`
2. Filters hooks to find ones with `command == "claude-rewind"`
3. Removes only Rewind hooks (preserves other hooks)
4. Writes updated settings back to file
5. Logs number of hooks removed

---

#### `get_registered_hooks()`

**Location**: `registration.py:188-208`

```python
def get_registered_hooks(
    project_root: Optional[Path] = None
) -> Dict[str, Dict[str, Any]]:
    """Get currently registered Rewind hooks.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Dictionary of registered Rewind hooks
    """
```

**Example:**
```python
hooks = get_registered_hooks()
# {
#     'PostToolUse': {
#         'command': 'claude-rewind',
#         'args': ['hook-handler', 'post-tool-use'],
#         'background': True,
#         'description': '...'
#     },
#     ...
# }
```

---

#### `is_hooks_registered()`

**Location**: `registration.py:211-220`

```python
def is_hooks_registered(project_root: Optional[Path] = None) -> bool:
    """Check if native hooks are registered.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        True if hooks are registered
    """
```

**Example:**
```python
if is_hooks_registered():
    print("Hooks are active!")
else:
    print("Hooks not registered")
```

---

### Helper Functions

#### `get_claude_settings_path()`

**Location**: `registration.py:16-28`

```python
def get_claude_settings_path(project_root: Optional[Path] = None) -> Path:
    """Get path to .claude/settings.json.

    Args:
        project_root: Project root directory. If None, uses current directory.

    Returns:
        Path to .claude/settings.json
    """
```

---

#### `load_claude_settings()`

**Location**: `registration.py:31-51`

```python
def load_claude_settings(settings_path: Path) -> Dict[str, Any]:
    """Load existing Claude settings.

    Args:
        settings_path: Path to settings.json

    Returns:
        Settings dictionary (empty if file doesn't exist)
    """
```

**Behavior:**
- Returns empty dict if file doesn't exist
- Catches `JSONDecodeError` and returns empty dict
- Logs warnings on failure

---

#### `save_claude_settings()`

**Location**: `registration.py:54-75`

```python
def save_claude_settings(
    settings_path: Path,
    settings: Dict[str, Any]
) -> None:
    """Save Claude settings to file.

    Args:
        settings_path: Path to settings.json
        settings: Settings dictionary to save

    Raises:
        HookRegistrationError: If save fails
    """
```

**Behavior:**
- Creates `.claude/` directory if needed
- Writes JSON with 2-space indentation
- Raises `HookRegistrationError` on failure

---

## Extension Guide

### Adding a New Hook Event Type

**Step 1**: Add to `HookEventType` enum

```python
# claude_rewind/native_hooks/events.py

class HookEventType(Enum):
    # ... existing events
    MY_CUSTOM_EVENT = "MyCustomEvent"
```

**Step 2**: Add fields to `HookEvent` dataclass (if needed)

```python
# claude_rewind/native_hooks/events.py

@dataclass
class HookEvent:
    # ... existing fields
    custom_field: Optional[str] = None
```

**Step 3**: Update `from_raw_data()` to extract custom fields

```python
# claude_rewind/native_hooks/events.py

@classmethod
def from_raw_data(cls, event_type_str: str, raw_data: Dict[str, Any]) -> "HookEvent":
    # ... existing parsing

    # Extract custom fields
    event.custom_field = raw_data.get('custom_field')

    return event
```

**Step 4**: Add handler to `NativeHookDispatcher`

```python
# claude_rewind/native_hooks/handlers.py

class NativeHookDispatcher:
    def __init__(self, project_root: Path):
        # ... existing initialization

        self._handlers[HookEventType.MY_CUSTOM_EVENT] = self._handle_my_custom_event

    def _handle_my_custom_event(self, event: HookEvent) -> None:
        """Handle MyCustomEvent."""
        description = f"Custom event: {event.custom_field}"
        tags = ['custom-event', f'session:{event.session_id}']

        snapshot_id = self.snapshot_engine.create_snapshot(
            description=description,
            tags=tags
        )
        logger.info(f"Created snapshot {snapshot_id} for custom event")
```

**Step 5**: Register hook in `register_native_hooks()`

```python
# claude_rewind/native_hooks/registration.py

def register_native_hooks(project_root: Optional[Path] = None) -> None:
    hooks_config = {
        # ... existing hooks
        "MyCustomEvent": {
            "command": "claude-rewind",
            "args": ["hook-handler", "my-custom-event"],
            "background": True,
            "description": "Handle custom events"
        }
    }
    # ... rest of function
```

---

### Custom Handler Logic

You can extend `NativeHookDispatcher` for custom behavior:

```python
from claude_rewind.native_hooks import NativeHookDispatcher
from pathlib import Path

class MyCustomDispatcher(NativeHookDispatcher):
    def _handle_post_tool_use(self, event: HookEvent) -> None:
        """Override default PostToolUse handler."""

        # Add custom logic
        if event.tool_name == "Edit":
            # Special handling for Edit tool
            print(f"Edit detected: {event.modified_files}")

        # Call original handler
        super()._handle_post_tool_use(event)

        # Post-processing
        self._notify_external_system(event)

    def _notify_external_system(self, event: HookEvent) -> None:
        """Custom notification logic."""
        # Send to external monitoring system
        pass
```

---

### Programmatic Registration

Register hooks programmatically instead of via CLI:

```python
from claude_rewind.native_hooks import register_native_hooks
from pathlib import Path

# Register for specific project
register_native_hooks(Path("/path/to/project"))

# Register for current directory
register_native_hooks()
```

---

### Testing Hooks

Create mock events for testing:

```python
from claude_rewind.native_hooks import HookEvent, NativeHookDispatcher
from claude_rewind.native_hooks.events import HookEventType
from datetime import datetime
from pathlib import Path

# Create mock event
event = HookEvent(
    event_type=HookEventType.POST_TOOL_USE,
    timestamp=datetime.now(),
    session_id="test-session",
    tool_name="Edit",
    prompt_context="Test change",
    modified_files=[Path("test.py")]
)

# Dispatch to handler
dispatcher = NativeHookDispatcher(Path.cwd())
dispatcher.dispatch(event)

# Verify snapshot was created
from claude_rewind.storage.database import DatabaseManager

db = DatabaseManager(Path(".claude-rewind/metadata.db"))
snapshots = db.list_snapshots(limit=1)
assert snapshots[0]['tags'] == ['auto', 'tool:Edit', 'session:test-session']
```

---

## Summary

The native hooks system provides:

1. **Event Types** - 10 event types (7 implemented, 3 future)
2. **Rich Data Structures** - `HookEvent` dataclass with extensive context
3. **Flexible Handlers** - Dispatcher pattern for routing events
4. **Easy Registration** - Simple API for managing hooks
5. **Extensibility** - Clean extension points for custom behavior

**Key Files:**
- `events.py` - Event types and data structures
- `handlers.py` - Event dispatcher and snapshot creation
- `registration.py` - Hook registration management

**Entry Point:**
```bash
claude-rewind hook-handler <event-type> <event-data-json>
```

**See Also:**
- `NATIVE_HOOKS_GUIDE.md` - User-facing documentation
- `USAGE_GUIDE.md` - General Rewind usage
- `COMPLETE_ROADMAP.md` - Future enhancements
