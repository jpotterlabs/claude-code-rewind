# 🎯 Claude Code Integration System

This document describes the sophisticated Claude Code integration system that implements the **original developer's vision** for automatic snapshot creation based on actual Claude Code actions.

## 🆚 Old vs New System

### ❌ Old System (Simple Watch Command)
- **Generic filesystem monitoring** using `watchdog`
- Created snapshots for **ANY** file change
- **No context** about what caused the change
- **High noise** - captured non-Claude changes
- **Limited intelligence** - just watched file timestamps

### ✅ New System (Claude Code Integration)
- **Intelligent Claude action detection** using multiple methods
- **Context-aware snapshots** with rich metadata
- **Action correlation** - knows what Claude tool was used
- **Session management** - tracks Claude Code sessions
- **Confidence scoring** - only captures high-confidence Claude actions
- **Multi-modal detection** - environment, processes, content analysis, file patterns

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Claude Code    │───▶│  Interceptor    │───▶│  Hook Manager   │
│  Actions        │    │  (Detection)    │    │  (Coordination) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                       │
                                ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Action Context │    │  Snapshot       │
                       │  (Metadata)     │    │  Engine         │
                       └─────────────────┘    └─────────────────┘
```

## 🧩 Core Components

### 1. ClaudeCodeInterceptor (`claude_interceptor.py`)
**Purpose**: Multi-modal detection system for Claude Code actions

**Detection Methods**:
- **Environment Detection**: Monitors for Claude processes, environment variables
- **File Pattern Analysis**: Analyzes file changes for Claude-specific patterns
- **Content Analysis**: Scans file content for AI-generated code signatures
- **Process Monitoring**: Tracks Claude-related processes
- **Confidence Scoring**: Rates each detection for reliability

**Key Features**:
```python
# Example usage
interceptor = ClaudeCodeInterceptor(project_root, config)
detected_actions = interceptor.detect_claude_actions()

for action in detected_actions:
    print(f"Tool: {action.tool_name}")
    print(f"Confidence: {action.estimated_confidence}")
    print(f"Method: {action.detection_method}")
    print(f"Files: {action.file_paths}")
```

### 2. ClaudeHookManager (`claude_hook_manager.py`)
**Purpose**: Orchestrates the complete Claude integration lifecycle

**Responsibilities**:
- **Session Management**: Tracks Claude Code sessions with unique IDs
- **Hook System**: Pre/post action hooks for extensibility
- **Automatic Snapshotting**: Creates snapshots for detected Claude actions
- **Action History**: Maintains history of recent Claude actions
- **Statistics**: Provides detailed session and performance metrics

**Key Features**:
```python
# Example usage
hook_manager = ClaudeHookManager(project_root, snapshot_engine, config)

# Register custom hooks
def my_pre_hook(action_context):
    print(f"About to execute: {action_context.action_type}")

hook_manager.register_pre_action_hook(my_pre_hook)
hook_manager.start_monitoring()
```

### 3. Enhanced CLI Commands

#### `claude-rewind monitor` (Replaces `watch`)
**The main monitoring command with advanced options**:

```bash
# Basic Claude Code monitoring
claude-rewind monitor

# Different monitoring modes
claude-rewind monitor --mode claude        # Pure Claude detection
claude-rewind monitor --mode filesystem    # Traditional file watching
claude-rewind monitor --mode hybrid        # Both methods combined

# Sensitivity levels
claude-rewind monitor --sensitivity high   # More aggressive detection
claude-rewind monitor --sensitivity low    # Only high-confidence actions

# Skip backup snapshot
claude-rewind monitor --no-backup
```

#### `claude-rewind session` (New)
**Manage Claude Code sessions**:

```bash
# Check session status
claude-rewind session

# Get detailed statistics
claude-rewind session --action stats

# Start monitoring session
claude-rewind session --action start

# Stop active session
claude-rewind session --action stop

# Show recent actions
claude-rewind session --show-recent 10
```

#### `claude-rewind watch` (Deprecated)
**Legacy command that guides users to the new system**.

## 🎯 Detection Algorithm

### Confidence Scoring System
Each detected action receives a confidence score (0.0 - 1.0):

- **0.6-0.7**: Possibly Claude action (file patterns, timing)
- **0.7-0.8**: Likely Claude action (content analysis, multiple indicators)
- **0.8-0.9**: Very likely Claude action (strong patterns, context)
- **0.9-1.0**: Almost certain Claude action (direct detection)

### Multi-Factor Detection
The system combines multiple signals:

1. **File Timing**: Multiple files changed within seconds
2. **Content Patterns**: AI-generated code signatures
3. **File Types**: Code files vs. other files
4. **Environment**: Claude processes, environment variables
5. **Naming Patterns**: Files with AI-typical names/structure

### Action Correlation
Different actions are detected based on patterns:

- **`edit_file`**: Existing file modified with code patterns
- **`create_file`**: New file with structured content
- **`multi_edit`**: Multiple files changed simultaneously
- **`delete_file`**: File removal in context of other changes

## 📊 Rich Metadata Capture

Each snapshot now includes detailed Claude-specific context:

```python
ActionContext(
    action_type="edit_file",           # Claude tool used
    timestamp=datetime.now(),          # Exact timing
    prompt_context="Claude edited...", # Description
    affected_files=[Path("file.py")],  # Files involved
    tool_name="claude_code",           # Tool identifier
    session_id="session_abc123"       # Session tracking
)
```

## 🔄 Session Management

### Session Lifecycle
1. **Session Start**: Creates unique session ID, starts monitoring
2. **Action Detection**: Continuously scans for Claude actions
3. **Snapshot Creation**: Creates context-rich snapshots
4. **Statistics Tracking**: Maintains real-time statistics
5. **Session End**: Clean shutdown with summary

### Session Statistics
- **Action Count**: Total Claude actions detected
- **Session Duration**: Time monitoring was active
- **Recent Actions**: Last N actions with details
- **Hook Counts**: Number of registered hooks
- **Detection Stats**: Performance metrics

## 🚀 Getting Started

### 1. Initialize Project
```bash
cd your-project
claude-rewind init
```

### 2. Start Monitoring
```bash
# Start intelligent Claude monitoring
claude-rewind monitor

# Or with custom settings
claude-rewind monitor --mode hybrid --sensitivity high
```

### 3. Use Claude Code
Open Claude Code and start making changes to your project. The system will automatically detect Claude actions and create snapshots.

### 4. View Results
```bash
# Check session status
claude-rewind session

# View timeline
claude-rewind timeline

# See what changed
claude-rewind diff <snapshot-id>

# Rollback if needed
claude-rewind rollback <snapshot-id>
```

## 🎛️ Configuration

The system respects all existing configuration options and adds new ones:

```yaml
hooks:
  claude_integration_enabled: true
  auto_snapshot_enabled: true
  pre_snapshot_script: null
  post_rollback_script: null

performance:
  max_file_size_mb: 100
  parallel_processing: true
  memory_limit_mb: 500
  snapshot_timeout_seconds: 30
  lazy_loading_enabled: true
  cache_size_limit: 10000
  target_snapshot_time_ms: 500
```

## 🧪 Testing

### Integration Test
Run the comprehensive test suite:
```bash
python test_integration.py
```

This tests:
- ✅ Hook manager initialization
- ✅ Action detection algorithms
- ✅ Snapshot creation with Claude context
- ✅ Session management
- ✅ Statistics tracking
- ✅ Cleanup and shutdown

### Manual Testing
1. Start monitoring: `claude-rewind monitor --verbose`
2. Use Claude Code to edit files
3. Watch console output for detected actions
4. Check timeline: `claude-rewind timeline`
5. Verify snapshots contain proper metadata

## 🔧 Troubleshooting

### Low Detection Rate
- Increase sensitivity: `--sensitivity high`
- Use hybrid mode: `--mode hybrid`
- Check verbose output: `--verbose`

### False Positives
- Decrease sensitivity: `--sensitivity low`
- Use pure Claude mode: `--mode claude`
- Adjust confidence thresholds in config

### Performance Issues
- Reduce check frequency in sensitivity settings
- Enable lazy loading in config
- Limit file size monitoring threshold

## 🎉 Benefits of New System

1. **🎯 Accurate Detection**: Only captures actual Claude actions
2. **📖 Rich Context**: Knows exactly what Claude did and when
3. **📊 Session Awareness**: Tracks complete Claude Code sessions
4. **🔧 Configurable**: Multiple modes and sensitivity levels
5. **📈 Scalable**: Efficient for large projects
6. **🧩 Extensible**: Hook system for custom behavior
7. **📱 User-Friendly**: Intuitive CLI with helpful feedback
8. **🚀 Future-Ready**: Architecture supports advanced features

## 🔮 Future Enhancements

The new architecture enables future features like:
- **Prompt Context Extraction**: Capture actual Claude prompts
- **Tool Parameter Tracking**: Record exact tool parameters used
- **Semantic Rollbacks**: Roll back by intent rather than just files
- **Claude Session Replay**: Replay entire Claude Code sessions
- **Integration Analytics**: Detailed insights into Claude Code usage
- **Smart Conflict Resolution**: Use Claude context for better merging

---

**🎯 This system fulfills the original developer's vision of sophisticated Claude Code integration, moving far beyond simple file watching to provide true action-aware snapshot management.**